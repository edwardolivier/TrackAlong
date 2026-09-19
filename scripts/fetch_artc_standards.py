#!/usr/bin/env python3
"""Download every document linked from an ARTC engineering standards page.

The ARTC extranet (https://extranet.artc.com.au) publishes its Track & Civil
engineering standards as plain HTML pages with links to PDF/DOC files, grouped
under section headings such as "Structures".  This script fetches one of those
pages, finds every linked document, and saves each one into an output folder,
one sub-folder per section heading.

Usage (defaults to the Track & Civil procedure page, all sections):

    python scripts/fetch_artc_standards.py

Only the "Structures" section:

    python scripts/fetch_artc_standards.py --section structures

Different page or output folder:

    python scripts/fetch_artc_standards.py \
        --url https://extranet.artc.com.au/eng_track-civil_procedure.html \
        --out standards/artc

Standard library only; no third-party packages required.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import Request, urlopen

DEFAULT_URL = "https://extranet.artc.com.au/eng_track-civil_procedure.html"
DEFAULT_OUT = "standards/artc"
DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".dwg", ".dxf")
USER_AGENT = "Mozilla/5.0 (compatible; TrackAlong standards fetcher)"


class DocumentLinkParser(HTMLParser):
    """Collect (section, anchor id, href, link text) for every document link.

    The current section is tracked from heading tags (h1-h6) and from the id
    of any element, so that a link to ``...html#structures`` maps onto the
    section named ``structures``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.section = "general"
        self.section_id = ""
        self._in_heading = False
        self._heading_text: list[str] = []
        self._current_href: str | None = None
        self._link_text: list[str] = []
        self.links: list[tuple[str, str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._in_heading = True
            self._heading_text = []
            if attr.get("id"):
                self.section_id = attr["id"] or ""
        elif attr.get("id") and tag in ("a", "div", "section", "span") and not attr.get("href"):
            # Anchor targets like <a id="structures"></a> or <div id="structures">
            self.section_id = attr["id"] or ""
            if not self._in_heading:
                self.section = attr["id"] or self.section
        if tag == "a" and attr.get("href"):
            self._current_href = attr["href"] or ""
            self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self._in_heading:
            self._in_heading = False
            text = " ".join("".join(self._heading_text).split())
            if text:
                self.section = text
        if tag == "a" and self._current_href is not None:
            href = self._current_href
            text = " ".join("".join(self._link_text).split())
            if href.lower().split("?")[0].endswith(DOC_EXTENSIONS):
                self.links.append((self.section, self.section_id, href, text))
            self._current_href = None

    def handle_data(self, data: str) -> None:
        if self._in_heading:
            self._heading_text.append(data)
        if self._current_href is not None:
            self._link_text.append(data)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "general"


def fetch(url: str, timeout: float = 60.0) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https host)
        return resp.read()


def collect_links(page_url: str, html: str) -> list[dict[str, str]]:
    parser = DocumentLinkParser()
    parser.feed(html)
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for section, section_id, href, text in parser.links:
        url = urljoin(page_url, href)
        if url in seen:
            continue
        seen.add(url)
        out.append(
            {
                "section": section,
                "section_id": section_id,
                "url": url,
                "text": text,
                "filename": unquote(Path(urlparse(url).path).name),
            }
        )
    return out


def wanted(link: dict[str, str], section_filter: str | None) -> bool:
    if not section_filter:
        return True
    want = section_filter.lower()
    return want in link["section"].lower() or want == link["section_id"].lower()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=DEFAULT_URL, help="ARTC standards page to scrape")
    ap.add_argument("--out", default=DEFAULT_OUT, help="Output folder (default: %(default)s)")
    ap.add_argument("--section", default=None, help="Only download links under this section heading / anchor id (e.g. structures)")
    ap.add_argument("--list", action="store_true", help="List the documents found and exit without downloading")
    ap.add_argument("--delay", type=float, default=0.5, help="Seconds to wait between downloads")
    args = ap.parse_args(argv)

    print(f"Fetching index page: {args.url}")
    html = fetch(args.url).decode("utf-8", errors="replace")
    links = [l for l in collect_links(args.url, html) if wanted(l, args.section)]
    if not links:
        print("No document links found (check --section, or the page layout may have changed).", file=sys.stderr)
        return 1

    print(f"Found {len(links)} document(s)")
    if args.list:
        for l in links:
            print(f"{l['section']:<40} {l['filename']:<45} {l['text']}")
        return 0

    out_root = Path(args.out)
    manifest_lines = ["section\tfilename\ttitle\turl"]
    failures = 0
    for i, l in enumerate(links, 1):
        dest_dir = out_root / slugify(l["section"])
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / l["filename"]
        manifest_lines.append(f"{l['section']}\t{l['filename']}\t{l['text']}\t{l['url']}")
        if dest.exists() and dest.stat().st_size > 0:
            print(f"[{i}/{len(links)}] skip (exists) {dest}")
            continue
        print(f"[{i}/{len(links)}] {l['url']} -> {dest}")
        try:
            dest.write_bytes(fetch(l["url"]))
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"    FAILED: {exc}", file=sys.stderr)
        time.sleep(args.delay)

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "manifest.tsv").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    print(f"Done. {len(links) - failures} downloaded, {failures} failed. Manifest: {out_root / 'manifest.tsv'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
