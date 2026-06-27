from __future__ import annotations

import csv
import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag


START_URL = "https://police.byu.edu/police-beat-list"
MAX_PAGES = 300
OUTPUT_CSV = Path("police_beat_raw.csv")
USER_AGENT = "BYU-Police-Beat-Scraper"
REQUEST_TIMEOUT_SECONDS = 15
# Keep this nonzero so the scraper is polite, but short enough for local iteration.
RATE_LIMIT_SECONDS = (0.25, 0.75)

CSV_COLUMNS = [
    "beat_url",
    "beat_title",
    "beat_published_at",
    "date_range_raw",
    "is_multi_date_beat",
    "incident_type",
    "incident_text",
    "scraped_at",
]

DATE_RE = re.compile(r"\d{2}/\d{2}/\d{4}")
POLICE_BEAT_TITLE_RE = re.compile(
    r"Police\s+Beat\s*(?:\u2022|[-:])\s*(?P<date_range>.+)$",
    re.IGNORECASE,
)
FOLLOW_FACEBOOK_RE = re.compile(r"Follow\s+us\s+on\s+Facebook", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"\s+")

LIST_ITEM_SELECTOR = "div.ListImageSmall-items-item"
DETAIL_CANDIDATE_SELECTORS = [
    ".RichTextArticleBody-body",
    ".RichTextArticleBody",
    ".ArticlePage-body",
    ".ArticlePage-articleBody",
    ".ContentPage-body",
    ".CreativeWorkPage-body",
    ".RichTextModule",
    ".RichTextFullWidth-content",
    ".RichTextFullWidth-items",
    ".RichTextFullWidth",
    ".PromoImageSmall-description",
    "article",
    "main.Page-main",
    "main",
]

NOISE_LINE_PREFIXES = (
    "overrideBackgroundColorOrImage=",
    "overrideTextColor=",
    "promoTextAlignment=",
    "overrideCardHideSection=",
    "overrideCardHideByline=",
    "overrideCardHideDescription=",
    "overridebuttonBgColor=",
    "overrideButtonText=",
    "data-content-type=",
)

NARRATIVE_START_WORDS = {
    "a",
    "an",
    "after",
    "as",
    "at",
    "authorities",
    "based",
    "byu",
    "campus",
    "dispatch",
    "during",
    "employees",
    "firefighters",
    "officer",
    "officers",
    "police",
    "provo",
    "security",
    "staff",
    "the",
    "they",
    "upon",
    "while",
}


@dataclass(frozen=True)
class BeatSummary:
    url: str
    title: str
    published_at: str
    date_range_raw: str
    is_multi_date_beat: bool


@dataclass(frozen=True)
class Incident:
    incident_type: str
    incident_text: str


class PoliceBeatScraper:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.request_count = 0

    def fetch_html(self, url: str) -> str | None:
        if self.request_count:
            delay = random.uniform(*RATE_LIMIT_SECONDS)
            logging.debug("Sleeping %.2f seconds before requesting %s", delay, url)
            time.sleep(delay)

        self.request_count += 1
        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            logging.warning("Request failed for %s: %s", url, exc)
            return None

        if response.status_code != 200:
            logging.warning("Non-200 response for %s: HTTP %s", url, response.status_code)
            return None

        return response.text

    def collect_beat_summaries(self, start_url: str, max_pages: int) -> list[BeatSummary]:
        summaries: list[BeatSummary] = []
        seen_urls: set[str] = set()
        next_page_url: str | None = start_url

        for page_number in range(1, max_pages + 1):
            if not next_page_url:
                break

            logging.info("Fetching list page %s: %s", page_number, next_page_url)
            html = self.fetch_html(next_page_url)
            if html is None:
                break

            try:
                page_summaries, next_page_url = parse_list_page(html, next_page_url)
            except Exception:
                logging.exception("Failed to parse list page %s", next_page_url)
                break

            new_count = 0
            for summary in page_summaries:
                if summary.url in seen_urls:
                    continue
                summaries.append(summary)
                seen_urls.add(summary.url)
                new_count += 1

            logging.info(
                "Collected %s new beat URLs from list page %s",
                new_count,
                page_number,
            )

        return summaries

    def scrape_incidents(self, summaries: Iterable[BeatSummary]) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []

        for summary in summaries:
            logging.info("Fetching beat detail: %s", summary.url)
            html = self.fetch_html(summary.url)
            if html is None:
                continue

            try:
                incidents = parse_detail_page(html)
            except Exception:
                logging.exception("Failed to parse beat detail %s", summary.url)
                continue

            scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            for incident in incidents:
                rows.append(
                    {
                        "beat_url": summary.url,
                        "beat_title": summary.title,
                        "beat_published_at": summary.published_at,
                        "date_range_raw": summary.date_range_raw,
                        "is_multi_date_beat": str(summary.is_multi_date_beat).lower(),
                        "incident_type": incident.incident_type,
                        "incident_text": incident.incident_text,
                        "scraped_at": scraped_at,
                    }
                )

            logging.info("Parsed %s incidents from %s", len(incidents), summary.url)

        return rows


def parse_list_page(html: str, page_url: str) -> tuple[list[BeatSummary], str | None]:
    soup = BeautifulSoup(html, "html.parser")
    summaries: list[BeatSummary] = []

    for item in soup.select(LIST_ITEM_SELECTOR):
        link = item.select_one("h3.PromoImageSmall-title a[href]")
        if not link:
            link = item.find("a", href=True, string=re.compile(r"Police\s+Beat", re.I))
        if not link:
            continue

        title = normalize_text(link.get_text(" ", strip=True))
        if not title.lower().startswith("police beat"):
            continue

        href = link.get("href")
        if not href:
            continue

        published_at = ""
        date_element = item.select_one(".PromoImageSmall-nameAndDate .date, span.date")
        if date_element:
            published_at = normalize_text(date_element.get_text(" ", strip=True))

        date_range_raw, is_multi_date_beat = parse_date_range(title)
        summaries.append(
            BeatSummary(
                url=urljoin(page_url, href),
                title=title,
                published_at=published_at,
                date_range_raw=date_range_raw,
                is_multi_date_beat=is_multi_date_beat,
            )
        )

    next_page_url = find_next_page_url(soup, page_url)
    return summaries, next_page_url


def find_next_page_url(soup: BeautifulSoup, page_url: str) -> str | None:
    for button in soup.select(".List-paginationButton[data-url]"):
        if re.search(r"\bNext\b", button.get_text(" ", strip=True), re.IGNORECASE):
            return urljoin(page_url, button["data-url"])

    for link in soup.find_all("a", href=True):
        if re.search(r"\bNext\b", link.get_text(" ", strip=True), re.IGNORECASE):
            return urljoin(page_url, link["href"])

    return None


def parse_date_range(title: str) -> tuple[str, bool]:
    match = POLICE_BEAT_TITLE_RE.search(title)
    if match:
        date_range_raw = normalize_text(match.group("date_range"))
    else:
        dates = DATE_RE.findall(title)
        date_range_raw = " - ".join(dates)

    is_multi_date_beat = len(DATE_RE.findall(date_range_raw)) > 1
    return date_range_raw, is_multi_date_beat


def parse_detail_page(html: str) -> list[Incident]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = find_detail_candidates(soup)
    best_incidents: list[Incident] = []

    for candidate in candidates:
        lines = extract_content_lines(candidate)
        incidents = parse_incident_lines(lines)
        if not incidents:
            incidents = parse_paragraph_incidents(candidate)
        if len(incidents) > len(best_incidents):
            best_incidents = incidents

    if not best_incidents:
        raise ValueError("No incidents parsed from detail page")

    return best_incidents


def find_detail_candidates(soup: BeautifulSoup) -> list[Tag]:
    candidates: list[Tag] = []
    seen: set[int] = set()

    for selector in DETAIL_CANDIDATE_SELECTORS:
        for tag in soup.select(selector):
            tag_id = id(tag)
            if tag_id not in seen:
                candidates.append(tag)
                seen.add(tag_id)

    for tag in soup.find_all(["div", "section"], recursive=True):
        text = tag.get_text(" ", strip=True)
        if FOLLOW_FACEBOOK_RE.search(text):
            tag_id = id(tag)
            if tag_id not in seen:
                candidates.append(tag)
                seen.add(tag_id)

    return candidates


def extract_content_lines(container: Tag) -> list[str]:
    clone = BeautifulSoup(str(container), "html.parser")

    for removable in clone.select(
        "script, style, svg, noscript, form, nav, header, footer, .RawHtmlModule"
    ):
        removable.decompose()

    for br in clone.find_all("br"):
        br.replace_with("\n")

    for block in clone.find_all(["p", "div", "section", "article", "li", "h1", "h2", "h3"]):
        block.insert_before("\n")
        block.insert_after("\n")

    text = clone.get_text("\n")
    lines: list[str] = []

    for raw_line in text.splitlines():
        line = normalize_text(raw_line)
        if FOLLOW_FACEBOOK_RE.search(line):
            break
        if is_noise_line(line):
            continue
        lines.append(line)

    return trim_blank_lines(lines)


def parse_incident_lines(lines: list[str]) -> list[Incident]:
    blocks = split_nonempty_blocks(lines)
    incidents: list[Incident] = []

    for block in blocks:
        block = [line for line in block if not is_title_or_date_line(line)]
        if len(block) < 2:
            continue

        incident_type = normalize_incident_type(block[0])
        incident_text = normalize_text(" ".join(block[1:]))
        if is_plausible_incident_type(incident_type) and incident_text:
            incidents.append(Incident(incident_type=incident_type, incident_text=incident_text))

    flat_lines = [line for line in lines if line and not is_title_or_date_line(line)]
    flat_incidents = parse_flat_incident_lines(flat_lines)
    if len(flat_incidents) > len(incidents):
        return flat_incidents

    if incidents:
        return incidents

    return flat_incidents


def parse_paragraph_incidents(container: Tag) -> list[Incident]:
    incidents: list[Incident] = []

    for paragraph in container.find_all("p"):
        text = normalize_text(paragraph.get_text(" ", strip=True))
        if not text or FOLLOW_FACEBOOK_RE.search(text):
            continue
        if is_title_or_date_line(text) or is_noise_line(text):
            continue
        incidents.append(Incident(incident_type="", incident_text=text))

    return incidents


def split_nonempty_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        if not line:
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)

    if current:
        blocks.append(current)

    return blocks


def parse_flat_incident_lines(lines: list[str]) -> list[Incident]:
    incidents: list[Incident] = []
    current_type: str | None = None
    current_text_parts: list[str] = []

    for line in lines:
        if is_strict_heading_candidate(line) and (current_type is None or current_text_parts):
            if current_type and current_text_parts:
                incidents.append(
                    Incident(
                        incident_type=normalize_incident_type(current_type),
                        incident_text=normalize_text(" ".join(current_text_parts)),
                    )
                )
            current_type = line
            current_text_parts = []
            continue

        if current_type:
            current_text_parts.append(line)

    if current_type and current_text_parts:
        incidents.append(
            Incident(
                incident_type=normalize_incident_type(current_type),
                incident_text=normalize_text(" ".join(current_text_parts)),
            )
        )

    return incidents


def is_plausible_incident_type(line: str) -> bool:
    if not line or len(line) > 100:
        return False
    if FOLLOW_FACEBOOK_RE.search(line):
        return False
    if is_title_or_date_line(line):
        return False
    if DATE_RE.search(line):
        return False
    if not re.search(r"[A-Za-z]", line):
        return False
    if len(line.split()) > 10:
        return False
    return True


def is_strict_heading_candidate(line: str) -> bool:
    if not is_plausible_incident_type(line):
        return False
    if line.endswith((".", "?", "!")):
        return False

    first_word = re.sub(r"[^A-Za-z']+", "", line.split()[0]).lower()
    if first_word in NARRATIVE_START_WORDS:
        return False

    return True


def is_title_or_date_line(line: str) -> bool:
    if not line:
        return False
    if line.lower().startswith("police beat"):
        return True
    if POLICE_BEAT_TITLE_RE.search(line):
        return True
    return False


def is_noise_line(line: str) -> bool:
    if not line:
        return False
    return any(line.startswith(prefix) for prefix in NOISE_LINE_PREFIXES)


def trim_blank_lines(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)

    while start < end and not lines[start]:
        start += 1
    while end > start and not lines[end - 1]:
        end -= 1

    return lines[start:end]


def normalize_incident_type(value: str) -> str:
    return normalize_text(value).rstrip(":")


def normalize_text(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value.replace("\xa0", " ")).strip()


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    scraper = PoliceBeatScraper()
    summaries = scraper.collect_beat_summaries(START_URL, MAX_PAGES)
    logging.info("Collected %s unique beat URLs", len(summaries))
    if not summaries:
        raise SystemExit("No beat URLs collected; leaving existing CSV untouched.")

    rows = scraper.scrape_incidents(summaries)
    if not rows:
        raise SystemExit("No incident rows parsed; leaving existing CSV untouched.")

    write_csv(rows, OUTPUT_CSV)
    logging.info("Wrote %s incident rows to %s", len(rows), OUTPUT_CSV)


if __name__ == "__main__":
    main()
