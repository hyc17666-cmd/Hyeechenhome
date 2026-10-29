#!/usr/bin/env python3
"""Collect title-level metadata from three newspapers and Qiushi.

Only titles, sections, dates, issue labels and source links are stored.
Article bodies are not stored or republished.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urldefrag, urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_FILE = BASE_DIR / "site" / "data" / "articles.json"
CHINA_TZ = timezone(timedelta(hours=8))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)

SOURCES = {
    "people": {"name": "人民日报", "order": 1},
    "guangming": {"name": "光明日报", "order": 2},
    "economic": {"name": "经济日报", "order": 3},
    "qiushi": {"name": "求是", "order": 4},
}

LOGGER = logging.getLogger("three-papers-one-journal")
EXCLUDED_TITLES = {"广告", "投稿网站", "关于经济日报社", "关于中国经济网"}
EXCLUDED_SECTIONS = {"广告"}
EXCLUDED_TITLE_PREFIXES = ("本版责编", "一版责编", "二版责编", "三版责编", "四版责编", "五版责编")


@dataclass
class Article:
    id: str
    source_key: str
    source_name: str
    source_order: int
    paper_date: str
    page: int | None
    position: int
    section: str
    issue: str | None
    title: str
    url: str
    fetched_at: str


class FetchError(RuntimeError):
    pass


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=1.0,
        status_forcelist=(408, 429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
    )
    return session


def fetch_html(session: requests.Session, url: str) -> tuple[str, str]:
    try:
        response = session.get(url, timeout=(15, 45), allow_redirects=True)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FetchError(f"{url}: {exc}") from exc
    # All four source families currently serve UTF-8 pages. Some People's Daily
    # responses nevertheless advertise GB2312 in headers, which causes mojibake.
    response.encoding = "utf-8"
    return response.text, response.url


def clean_text(value: str | None) -> str:
    return " ".join((value or "").split())


def parse_section(value: str) -> tuple[int | None, str]:
    value = clean_text(value)
    match = re.search(r"(?:第\s*)?(\d+)\s*版\s*[：:]?\s*(.*)", value)
    if match:
        return int(match.group(1)), clean_text(match.group(2))
    return None, value


def normalize_title(value: str) -> str:
    return re.sub(r"[\s\u3000]+", "", clean_text(value)).lower()


def make_article(
    source_key: str,
    paper_date: date,
    page: int | None,
    section: str,
    title: str,
    url: str,
    fetched_at: str,
    position: int = 0,
    issue: str | None = None,
) -> Article:
    title = clean_text(title)
    section = clean_text(section)
    clean_url, _ = urldefrag(url)
    raw_id = f"{source_key}|{paper_date.isoformat()}|{issue or ''}|{clean_url}|{title}"
    article_id = hashlib.sha1(raw_id.encode("utf-8")).hexdigest()[:16]
    source = SOURCES[source_key]
    return Article(
        id=article_id,
        source_key=source_key,
        source_name=source["name"],
        source_order=source["order"],
        paper_date=paper_date.isoformat(),
        page=page,
        position=position,
        section=section,
        issue=issue,
        title=title,
        url=clean_url,
        fetched_at=fetched_at,
    )


def dedupe_articles(articles: Iterable[Article]) -> list[Article]:
    result: list[Article] = []
    seen: set[tuple[str, str]] = set()
    for article in articles:
        key = (
            article.source_key,
            article.url if article.source_key == "qiushi" else normalize_title(article.title),
        )
        if (
            not article.title
            or article.title in EXCLUDED_TITLES
            or any(article.title.startswith(prefix) for prefix in EXCLUDED_TITLE_PREFIXES)
            or article.section in EXCLUDED_SECTIONS
            or key in seen
        ):
            continue
        seen.add(key)
        result.append(article)
    return result


def section_urls(
    soup: BeautifulSoup,
    base_url: str,
    pattern: re.Pattern[str],
) -> list[str]:
    urls: list[str] = []
    for anchor in soup.find_all("a", href=True):
        candidate, _ = urldefrag(urljoin(base_url, anchor["href"]))
        if pattern.search(candidate) and candidate not in urls:
            urls.append(candidate)

    def page_number(url: str) -> int:
        match = re.search(r"node_(\d+)\.html$", url)
        return int(match.group(1)) if match else 999

    return sorted(urls, key=page_number)


def scrape_people(session: requests.Session, paper_date: date, fetched_at: str) -> list[Article]:
    month = paper_date.strftime("%Y%m")
    day = paper_date.strftime("%d")
    first_url = f"https://paper.people.com.cn/rmrb/pc/layout/{month}/{day}/node_01.html"
    html, final_url = fetch_html(session, first_url)
    soup = BeautifulSoup(html, "html.parser")
    node_pattern = re.compile(r"/rmrb/pc/layout/\d{6}/\d{2}/node_\d+\.html$")
    nodes = section_urls(soup, final_url, node_pattern)
    if not nodes:
        nodes = [final_url]

    articles: list[Article] = []
    for node_url in nodes:
        if node_url != final_url:
            page_html, node_final_url = fetch_html(session, node_url)
            time.sleep(0.22)
        else:
            page_html, node_final_url = html, final_url
        node_soup = BeautifulSoup(page_html, "html.parser")

        page: int | None = None
        section = ""
        for anchor in node_soup.find_all("a", href=True):
            candidate, _ = urldefrag(urljoin(node_final_url, anchor["href"]))
            if candidate.rstrip("/") == node_final_url.rstrip("/"):
                page, section = parse_section(clean_text(anchor.get_text(" ", strip=True)))
                if page is not None:
                    break

        for position, anchor in enumerate(node_soup.find_all("a", href=True), start=1):
            title = clean_text(anchor.get_text(" ", strip=True))
            article_url, _ = urldefrag(urljoin(node_final_url, anchor["href"]))
            if not title or not re.search(r"/rmrb/pc/content/\d{6}/\d{2}/content_\d+\.html$", article_url):
                continue
            articles.append(
                make_article(
                    "people", paper_date, page, section, title, article_url, fetched_at,
                    position=position,
                )
            )
    return dedupe_articles(articles)


def scrape_guangming(session: requests.Session, paper_date: date, fetched_at: str) -> list[Article]:
    month = paper_date.strftime("%Y%m")
    day = paper_date.strftime("%d")
    first_url = f"https://epaper.gmw.cn/gmrb/html/layout/{month}/{day}/node_01.html"
    html, final_url = fetch_html(session, first_url)
    soup = BeautifulSoup(html, "html.parser")
    node_pattern = re.compile(r"/gmrb/html/layout/\d{6}/\d{2}/node_\d+\.html$")
    nodes = section_urls(soup, final_url, node_pattern)
    if not nodes:
        nodes = [final_url]

    articles: list[Article] = []
    for node_url in nodes:
        if node_url != final_url:
            page_html, node_final_url = fetch_html(session, node_url)
            time.sleep(0.22)
        else:
            page_html, node_final_url = html, final_url
        node_soup = BeautifulSoup(page_html, "html.parser")
        page_title = clean_text(node_soup.title.get_text(" ", strip=True) if node_soup.title else "")
        match = re.search(r"第\s*(\d+)\s*版\s*[：:]\s*(.*?)_光明网", page_title)
        if match:
            page, section = int(match.group(1)), clean_text(match.group(2))
        else:
            page, section = parse_section(page_title.split("_", 1)[0])

        for position, anchor in enumerate(node_soup.find_all("a", href=True), start=1):
            title = clean_text(anchor.get_text(" ", strip=True))
            article_url, _ = urldefrag(urljoin(node_final_url, anchor["href"]))
            if not title or not re.search(r"/gmrb/html/content/\d{6}/\d{2}/content_\d+\.html$", article_url):
                continue
            articles.append(
                make_article(
                    "guangming", paper_date, page, section, title, article_url, fetched_at,
                    position=position,
                )
            )
    return dedupe_articles(articles)


def scrape_economic(session: requests.Session, paper_date: date, fetched_at: str) -> list[Article]:
    month = paper_date.strftime("%Y%m")
    day = paper_date.strftime("%d")
    first_url = f"http://paper.ce.cn/pc/layout/{month}/{day}/node_01.html"
    html, final_url = fetch_html(session, first_url)
    soup = BeautifulSoup(html, "html.parser")
    node_pattern = re.compile(r"/pc/layout/\d{6}/\d{2}/node_\d+\.html$")
    nodes = section_urls(soup, final_url, node_pattern)
    if not nodes:
        nodes = [final_url]

    articles: list[Article] = []
    for node_url in nodes:
        if node_url != final_url:
            page_html, node_final_url = fetch_html(session, node_url)
            time.sleep(0.22)
        else:
            page_html, node_final_url = html, final_url
        node_soup = BeautifulSoup(page_html, "html.parser")

        page: int | None = None
        section = ""
        for anchor in node_soup.find_all("a", href=True):
            candidate, _ = urldefrag(urljoin(node_final_url, anchor["href"]))
            if candidate.rstrip("/") == node_final_url.rstrip("/"):
                page, section = parse_section(clean_text(anchor.get_text(" ", strip=True)))
                if page is not None:
                    break

        for position, anchor in enumerate(node_soup.find_all("a", href=True), start=1):
            title = clean_text(anchor.get_text(" ", strip=True))
            article_url, _ = urldefrag(urljoin(node_final_url, anchor["href"]))
            if not title or not re.search(r"/pc/content/\d{6}/\d{2}/content_\d+\.html$", article_url):
                continue
            articles.append(
                make_article(
                    "economic", paper_date, page, section, title, article_url, fetched_at,
                    position=position,
                )
            )
    return dedupe_articles(articles)


def scrape_qiushi(session: requests.Session, paper_date: date, fetched_at: str) -> list[Article]:
    """Collect the current issue shown on the Qiushi homepage.

    Qiushi is semimonthly, so its issue date is not the daily aggregate date.
    The issue label (for example 2026/20) is stored separately and displayed
    in place of a newspaper date on the card.
    """
    url = "https://www.qstheory.cn/"
    html, final_url = fetch_html(session, url)
    soup = BeautifulSoup(html, "html.parser")

    issue_candidates: list[tuple[int, int, str]] = []
    for text in soup.find_all(string=re.compile(r"20\d{2}/\d{1,2}")):
        for year, number in re.findall(r"(20\d{2})/(\d{1,2})", str(text)):
            issue_candidates.append((int(year), int(number), f"{year}/{int(number):02d}"))
    if not issue_candidates:
        raise FetchError("求是首页未找到期号")
    latest = max(issue_candidates)
    issue = latest[2]

    articles: list[Article] = []
    position = 0

    def add_from_anchor(anchor, section: str) -> None:
        nonlocal position
        if anchor is None:
            return
        article_url, _ = urldefrag(urljoin(final_url, anchor.get("href", "")))
        if not re.search(r"/20\d{6}/[0-9a-f]{32}/c\.html$", article_url):
            return
        title = clean_text(anchor.get_text(" ", strip=True))
        if not title:
            return
        position += 1
        articles.append(
            make_article(
                "qiushi", paper_date, None, section, title, article_url, fetched_at,
                position=position, issue=issue,
            )
        )

    # The homepage hero carousel highlights the current issue's lead pieces.
    for slide in soup.select(".swiper-slide"):
        anchor = slide.select_one("h2 a") or slide.select_one("a[href]")
        add_from_anchor(anchor, "本期要目")

    # Current-issue cards.
    for card in soup.select(".qs-card"):
        meta = card.select_one(".qs-card-meta")
        if not meta or issue not in clean_text(meta.get_text(" ", strip=True)):
            continue
        section_el = card.select_one(".qs-card-title")
        section = clean_text(section_el.get_text(" ", strip=True)) if section_el else "本期文章"
        anchor = card.select_one(".qs-card-content a") or card.select_one("a[href]")
        add_from_anchor(anchor, section)

    # Current-issue media cards.
    for item in soup.select(".qs-media-item"):
        meta = item.select_one(".qs-media-item-content span")
        if not meta or issue not in clean_text(meta.get_text(" ", strip=True)):
            continue
        block = item.find_parent(class_="qs-media-block")
        block_title = block.select_one(".qs-list-block-title") if block else None
        section = clean_text(block_title.get_text(" ", strip=True)) if block_title else "本期文章"
        add_from_anchor(item.select_one(".qs-media-item-content a"), section)

    # Current-issue list items.
    for item in soup.select("li"):
        if not any(issue in clean_text(span.get_text(" ", strip=True)) for span in item.find_all("span")):
            continue
        block = item.find_parent(class_="qs-media-block")
        block_title = block.select_one(".qs-list-block-title") if block else None
        section = clean_text(block_title.get_text(" ", strip=True)) if block_title else "本期文章"
        add_from_anchor(item.find("a", href=True), section)

    return dedupe_articles(articles)


SCRAPERS: dict[str, Callable[[requests.Session, date, str], list[Article]]] = {
    "people": scrape_people,
    "guangming": scrape_guangming,
    "economic": scrape_economic,
    "qiushi": scrape_qiushi,
}


def scrape_with_fallback(
    source_key: str,
    session: requests.Session,
    latest_date: date,
    fetched_at: str,
) -> tuple[date | None, list[Article], str | None]:
    errors: list[str] = []
    if source_key == "qiushi":
        try:
            LOGGER.info("求是: trying current issue")
            articles = scrape_qiushi(session, latest_date, fetched_at)
            if articles:
                return latest_date, articles, None
            errors.append("首页未找到当前期文章")
        except Exception as exc:
            errors.append(str(exc))
            LOGGER.warning("求是 failed: %s", exc)
        return None, [], "; ".join(errors)

    scraper = SCRAPERS[source_key]
    for offset in range(0, 4):
        paper_date = latest_date - timedelta(days=offset)
        try:
            LOGGER.info("%s: trying %s", SOURCES[source_key]["name"], paper_date)
            articles = scraper(session, paper_date, fetched_at)
            if articles:
                return paper_date, articles, None
            errors.append(f"{paper_date}: 无文章")
        except Exception as exc:
            errors.append(f"{paper_date}: {exc}")
            LOGGER.warning("%s %s failed: %s", source_key, paper_date, exc)
        time.sleep(0.8)
    return None, [], "; ".join(errors)


def load_existing(path: Path) -> dict:
    if not path.exists():
        return {"articles": [], "sources_status": []}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Cannot read existing data, starting fresh: %s", exc)
        return {"articles": [], "sources_status": []}


def merge_data(
    existing: dict,
    updates: dict[str, tuple[date | None, list[Article], str | None]],
    latest_date: date,
    generated_at: str,
    keep_days: int,
) -> dict:
    old_articles = [
        article for article in existing.get("articles", [])
        if article.get("source_key") in SOURCES
    ]
    replaced = {
        (source_key, paper_date.isoformat())
        for source_key, (paper_date, _articles, _error) in updates.items()
        if paper_date is not None
    }

    articles = [
        article
        for article in old_articles
        if (article.get("source_key"), article.get("paper_date")) not in replaced
    ]

    # Qiushi is semimonthly; keep only the current issue in the rolling data.
    if updates.get("qiushi", (None, [], None))[0] is not None:
        articles = [article for article in articles if article.get("source_key") != "qiushi"]

    for _source_key, (paper_date, new_articles, _error) in updates.items():
        if paper_date is not None:
            articles.extend(asdict(article) for article in new_articles)

    cutoff = (latest_date - timedelta(days=keep_days - 1)).isoformat()
    articles = [article for article in articles if article.get("paper_date", "") >= cutoff]
    articles.sort(
        key=lambda article: (
            int(article.get("page") or 999),
            int(article.get("position") or 9999),
            article.get("title", ""),
        )
    )
    articles.sort(key=lambda article: int(article.get("source_order", 99)))
    articles.sort(key=lambda article: article.get("paper_date", ""), reverse=True)

    statuses = []
    for source_key, (paper_date, new_articles, error) in updates.items():
        statuses.append(
            {
                "source_key": source_key,
                "source_name": SOURCES[source_key]["name"],
                "status": "ok" if paper_date is not None else "error",
                "paper_date": paper_date.isoformat() if paper_date else None,
                "issue": new_articles[0].issue if new_articles else None,
                "count": len(new_articles),
                "error": error,
            }
        )

    return {
        "generated_at": generated_at,
        "timezone": "Asia/Shanghai",
        "latest_paper_date": latest_date.isoformat(),
        "keep_days": keep_days,
        "total": len(articles),
        "sources_status": statuses,
        "articles": articles,
    }


def run(args: argparse.Namespace) -> int:
    latest_date = date.fromisoformat(args.date) if args.date else datetime.now(CHINA_TZ).date()
    fetched_at = datetime.now(CHINA_TZ).isoformat(timespec="seconds")
    session = make_session()
    updates = {
        source_key: scrape_with_fallback(source_key, session, latest_date, fetched_at)
        for source_key in SCRAPERS
    }
    data = merge_data(load_existing(args.data_file), updates, latest_date, fetched_at, args.keep_days)
    args.data_file.parent.mkdir(parents=True, exist_ok=True)
    args.data_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for status in data["sources_status"]:
        if status["status"] == "ok":
            suffix = f" {status['issue']}" if status.get("issue") else ""
            print(f"{status['source_name']}: {status['count']} 篇 ({status['paper_date']}{suffix})")
        else:
            print(f"{status['source_name']}: 失败 - {status['error']}", file=sys.stderr)
    print(f"数据已写入 {args.data_file}，共 {data['total']} 条")
    return 0 if any(status["status"] == "ok" for status in data["sources_status"]) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取三报一刊标题与原文链接")
    parser.add_argument("--date", help="指定报纸日期，格式 YYYY-MM-DD；默认使用北京时间当天")
    parser.add_argument("--keep-days", type=int, default=30, help="保留最近多少天的数据，默认 30")
    parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE, help="输出 JSON 路径")
    parser.add_argument("--verbose", action="store_true", help="输出详细日志")
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if arguments.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    raise SystemExit(run(arguments))
