#!/usr/bin/env python3
"""Command line tool to gather SEO-related insights from Trendyol (or any URL).

The script downloads the HTML of the provided URL and extracts useful SEO data
such as title, meta description, headings, link distribution, and image
accessibility information. Results are printed to the console and can optionally
be exported as JSON for further analysis.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


_TEXT_SPLIT_RE = re.compile(r"\s+")


@dataclass
class HeadingData:
    tag: str
    text: str


class SEOHTMLParser(HTMLParser):
    """HTML parser that collects SEO-related metrics from a page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.current_heading: Optional[str] = None
        self.heading_buffer: List[str] = []
        self.skip_content: Optional[str] = None

        self.title: str = ""
        self.meta_description: Optional[str] = None
        self.meta_robots: Optional[str] = None
        self.canonical_link: Optional[str] = None
        self.viewport: Optional[str] = None

        self.headings: Dict[str, List[HeadingData]] = defaultdict(list)
        self.word_count: int = 0
        self.links: List[str] = []
        self.images_total: int = 0
        self.images_missing_alt: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        attrs_dict = {name.lower(): (value or "") for name, value in attrs}

        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            name = attrs_dict.get("name", "").lower()
            prop = attrs_dict.get("property", "").lower()
            content = attrs_dict.get("content")

            if name == "description" and content and not self.meta_description:
                self.meta_description = content.strip()
            elif name == "robots" and content and not self.meta_robots:
                self.meta_robots = content.strip()
            elif prop == "og:description" and content and not self.meta_description:
                # Fallback to Open Graph description when standard meta is missing.
                self.meta_description = content.strip()
        elif tag == "link":
            rel = attrs_dict.get("rel", "").lower()
            href = attrs_dict.get("href")
            if href and "canonical" in rel and not self.canonical_link:
                self.canonical_link = href.strip()
        elif tag in {"script", "style"}:
            self.skip_content = tag
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.current_heading = tag
            self.heading_buffer = []
        elif tag == "img":
            self.images_total += 1
            alt_text = attrs_dict.get("alt", "").strip()
            if not alt_text:
                src = attrs_dict.get("src", "").strip() or "<unknown>"
                self.images_missing_alt.append(src)
        elif tag == "a":
            href = attrs_dict.get("href", "").strip()
            if href:
                self.links.append(href)

        if tag == "meta" and attrs_dict.get("name", "").lower() == "viewport":
            content = attrs_dict.get("content")
            if content and not self.viewport:
                self.viewport = content.strip()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag == "title":
            self.in_title = False
        elif tag in {"script", "style"} and self.skip_content == tag:
            self.skip_content = None
        elif tag == self.current_heading and self.current_heading is not None:
            text = " ".join(self.heading_buffer).strip()
            if text:
                self.headings[self.current_heading].append(HeadingData(tag=self.current_heading, text=text))
            self.current_heading = None
            self.heading_buffer = []

    def handle_data(self, data: str) -> None:
        if self.skip_content:
            return

        if self.in_title:
            self.title += data
        if self.current_heading is not None:
            self.heading_buffer.append(data)

        words = [w for w in _TEXT_SPLIT_RE.split(data) if w]
        self.word_count += len(words)


@dataclass
class SEOReport:
    url: str
    status_code: Optional[int]
    title: str
    title_length: int
    meta_description: Optional[str]
    meta_description_length: int
    canonical_url: Optional[str]
    robots: Optional[str]
    viewport: Optional[str]
    word_count: int
    headings: Dict[str, List[str]]
    links_total: int
    internal_links: int
    external_links: int
    images_total: int
    images_missing_alt: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "url": self.url,
            "status_code": self.status_code,
            "title": self.title,
            "title_length": self.title_length,
            "meta_description": self.meta_description,
            "meta_description_length": self.meta_description_length,
            "canonical_url": self.canonical_url,
            "robots": self.robots,
            "viewport": self.viewport,
            "word_count": self.word_count,
            "headings": self.headings,
            "links": {
                "total": self.links_total,
                "internal": self.internal_links,
                "external": self.external_links,
            },
            "images": {
                "total": self.images_total,
                "missing_alt": self.images_missing_alt,
            },
        }


def fetch_html(url: str, timeout: int = 20) -> Tuple[Optional[int], str]:
    """Fetch the HTML content for the given URL using a desktop browser user-agent."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    request = Request(url, headers=headers)

    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = getattr(response, "status", None)
            charset = response.headers.get_content_charset() or "utf-8"
            html_bytes = response.read()
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")
    except URLError as exc:  # pragma: no cover - network failure path
        print(f"URL error: {exc.reason}", file=sys.stderr)
        return None, ""

    try:
        html = html_bytes.decode(charset, errors="replace")
    except LookupError:
        html = html_bytes.decode("utf-8", errors="replace")

    return status_code, html


def analyze_html(url: str, html: str, status_code: Optional[int] = None) -> SEOReport:
    parser = SEOHTMLParser()
    parser.feed(html)

    parsed_url = urlparse(url)
    base_domain = parsed_url.netloc
    internal_links = 0
    external_links = 0

    for link in parser.links:
        normalized = urljoin(url, link)
        link_domain = urlparse(normalized).netloc
        if not link_domain or link_domain == base_domain:
            internal_links += 1
        else:
            external_links += 1

    headings_clean = {
        level: [entry.text for entry in entries]
        for level, entries in parser.headings.items()
    }

    title = parser.title.strip()
    meta_description = parser.meta_description.strip() if parser.meta_description else None

    return SEOReport(
        url=url,
        status_code=status_code,
        title=title,
        title_length=len(title),
        meta_description=meta_description,
        meta_description_length=len(meta_description) if meta_description else 0,
        canonical_url=parser.canonical_link,
        robots=parser.meta_robots,
        viewport=parser.viewport,
        word_count=parser.word_count,
        headings=headings_clean,
        links_total=len(parser.links),
        internal_links=internal_links,
        external_links=external_links,
        images_total=parser.images_total,
        images_missing_alt=parser.images_missing_alt,
    )


def analyze(url: str) -> SEOReport:
    status_code, html = fetch_html(url)
    return analyze_html(url, html, status_code=status_code)


def print_report(report: SEOReport) -> None:
    """Pretty-print the SEO report to STDOUT."""
    print("==== Trendyol SEO Bot Raporu ====")
    print(f"Hedef URL: {report.url}")
    print(f"HTTP Durumu: {report.status_code if report.status_code is not None else 'Bilinmiyor'}")
    print(f"Sayfa Başlığı ({report.title_length} karakter): {report.title or '-'}")
    print(
        "Meta Açıklaması ({} karakter): {}".format(
            report.meta_description_length,
            report.meta_description or "-",
        )
    )
    print(f"Kanonik URL: {report.canonical_url or '-'}")
    print(f"Robots Meta: {report.robots or '-'}")
    print(f"Viewport Meta: {report.viewport or '-'}")
    print(f"Kelime Sayısı (yaklaşık): {report.word_count}")
    print()

    print("--- Başlıklar ---")
    if not report.headings:
        print("Başlık etiketi bulunamadı.")
    else:
        for level in sorted(report.headings.keys()):
            items = report.headings[level]
            print(f"{level.upper()} ({len(items)} adet):")
            for idx, text in enumerate(items, start=1):
                print(f"  {idx}. {text}")
    print()

    print("--- Link Dağılımı ---")
    print(f"Toplam link: {report.links_total}")
    print(f"İç link sayısı: {report.internal_links}")
    print(f"Dış link sayısı: {report.external_links}")
    print()

    print("--- Görsel Analizi ---")
    print(f"Toplam görsel: {report.images_total}")
    print(f"Alt metni eksik görseller: {len(report.images_missing_alt)}")
    if report.images_missing_alt:
        for src in report.images_missing_alt[:10]:
            print(f"  - {src}")
        if len(report.images_missing_alt) > 10:
            print(f"  ... toplam {len(report.images_missing_alt)} görselde alt metni bulunmuyor")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trendyol veya benzeri siteler için SEO raporu oluşturan bot."
    )
    parser.add_argument(
        "url",
        help="Analiz edilecek sayfanın URL'si (varsayılan Trendyol ana sayfası)",
        nargs="?",
        default="https://www.trendyol.com/",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Sonucu JSON formatında kaydetmek için dosya yolu",
    )
    parser.add_argument(
        "--html-file",
        help="İnternet bağlantısı olmadan analiz için yerel bir HTML dosyası kullan",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if args.html_file:
        html_path = Path(args.html_file)
        if not html_path.exists():
            print(f"Belirtilen HTML dosyası bulunamadı: {html_path}", file=sys.stderr)
            return 1
        html = html_path.read_text(encoding="utf-8")
        report = analyze_html(args.url, html)
    else:
        report = analyze(args.url)

    print_report(report)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"\nRapor JSON olarak kaydedildi: {args.output}")

    return 0


if __name__ == "__main__":  # pragma: no cover - direct execution guard
    sys.exit(main())
