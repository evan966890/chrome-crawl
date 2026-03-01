#!/usr/bin/env python3
"""
IMA Knowledge Base Batch Crawler

Fetch all articles from an IMA knowledge base (ima.qq.com) and extract
them to clean HTML + Markdown with local images.

Phases:
  --phase=list   Fetch article list via IMA API → manifest.json
  --phase=crawl  Download + extract each article (with checkpoint resume)
  --phase=stats  Show crawl statistics
  --phase=retry  Re-process failed articles

Usage:
  # Step 1: Get article list (requires auth headers from CDP interception)
  python3 ima_crawl.py --phase=list --headers=/tmp/ima_headers.json

  # Step 2: Crawl all articles (or first N with --limit)
  python3 ima_crawl.py --phase=crawl -o ./output/ --limit=10

  # Resume after interruption (just run again)
  python3 ima_crawl.py --phase=crawl -o ./output/

IMA share_id is loaded from ~/.chrome-crawl/config.json:
  {"ima": {"share_id": "..."}}
Or pass via --share-id=<id>.
"""

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

# Import the extraction module from the same directory
sys.path.insert(0, str(Path(__file__).parent))
from wechat_extract import extract_article, safe_dirname

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_DIR = Path.home() / ".chrome-crawl" / "ima_kb"

IMA_API_URL = "https://ima.qq.com/cgi-bin/knowledge_share_get/get_share_info"
PAGE_LIMIT = 50  # articles per API page

# CDP settings
CDP_FETCH_SCRIPT = Path(__file__).parent / "cdp_fetch.js"
CDP_PORT_FILES = [
    Path.home() / ".chrome-crawl" / "cdp-port",
    Path.home() / ".openclaw" / "chrome-debug-port",
]
CDP_TMP_FILE = Path("/tmp/ima_cdp_fetch.html")

# Anti-crawl settings (relaxed for CDP mode — real browser fingerprint)
DELAY_MIN = 2.0
DELAY_MAX = 5.0
PAUSE_EVERY = 200       # pause after every N articles
PAUSE_DURATION = 20     # seconds
BACKOFF_BASE = 5        # seconds (exponential: 5, 15, 45)
MAX_RETRIES = 3
RATE_LIMIT_PAUSE = 60   # seconds on anti-crawl page


def _load_config() -> dict:
    config_path = Path.home() / ".chrome-crawl" / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _get_share_id(cli_share_id: str = None) -> str:
    if cli_share_id:
        return cli_share_id
    sid = os.environ.get("IMA_SHARE_ID")
    if sid:
        return sid
    config = _load_config()
    sid = config.get("ima", {}).get("share_id")
    if sid:
        return sid
    raise RuntimeError(
        "IMA share_id not found. Either:\n"
        "  1. Pass --share-id=<id>\n"
        "  2. Set IMA_SHARE_ID environment variable\n"
        '  3. Add to ~/.chrome-crawl/config.json: {"ima": {"share_id": "..."}}'
    )


# ---------------------------------------------------------------------------
# Manifest management
# ---------------------------------------------------------------------------

def load_manifest(base_dir: Path) -> list:
    manifest_path = base_dir / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return []


def save_manifest(articles: list, base_dir: Path):
    manifest_path = base_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(articles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Phase 1: Fetch article list from IMA API
# ---------------------------------------------------------------------------

def fetch_article_list(base_dir: Path, share_id: str,
                       headers_file: str = None, headers_json: str = None):
    """Fetch all articles from IMA API using cursor pagination."""
    # Load auth headers
    if headers_file and Path(headers_file).exists():
        auth_headers = json.loads(Path(headers_file).read_text())
    elif headers_json:
        auth_headers = json.loads(headers_json)
    else:
        existing = load_manifest(base_dir)
        if existing:
            print(f"Found existing manifest with {len(existing)} articles.")
            print("To refresh, provide --headers=<path> with auth headers.")
            return existing
        print("ERROR: No auth headers provided and no existing manifest.")
        print("Capture headers from CDP and provide via --headers=<path>")
        sys.exit(1)

    session = requests.Session()
    session.headers.update(auth_headers)

    all_articles = []
    cursor = ""
    page = 0

    while True:
        page += 1
        payload = {
            "share_id": share_id,
            "cursor": cursor,
            "limit": PAGE_LIMIT,
            "folder_id": "",
        }

        print(f"Fetching page {page} (cursor={cursor[:20] + '...' if cursor else 'start'})...")
        try:
            resp = session.post(IMA_API_URL, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code", -1) != 0:
                print(f"  API error: code={data.get('code')}, msg={data.get('msg')}")
                break
        except Exception as e:
            print(f"  ERROR on page {page}: {e}")
            break

        knowledge_list = data.get("knowledge_list", [])
        if not knowledge_list:
            print(f"  No more articles on page {page}.")
            break

        for item in knowledge_list:
            article = {
                "title": item.get("title", "Untitled"),
                "source_path": item.get("source_path", ""),
                "media_id": item.get("media_id", ""),
                "media_state": item.get("media_state", 0),
                "media_type": item.get("media_type", 0),
                "create_time": item.get("create_time", ""),
                "status": "pending",
                "dir_name": "",
                "errors": [],
            }
            all_articles.append(article)

        count = len(knowledge_list)
        total = len(all_articles)
        is_end = data.get("is_end", False)
        total_size = data.get("total_size", "?")
        print(f"  Got {count} articles (total: {total}/{total_size}, is_end={is_end})")

        if is_end:
            print("Reached end of list.")
            break

        next_cursor = data.get("next_cursor", "")
        if not next_cursor:
            print("No more pages (empty next_cursor).")
            break
        cursor = next_cursor

        time.sleep(random.uniform(1, 2))

    # Assign sequence numbers
    for idx, a in enumerate(all_articles):
        a["seq"] = idx + 1

    save_manifest(all_articles, base_dir)
    manifest_path = base_dir / "manifest.json"
    print(f"\nSaved manifest: {manifest_path}")
    print(f"Total articles: {len(all_articles)}")

    ready = sum(1 for a in all_articles if a.get("media_state") == 2)
    pending = sum(1 for a in all_articles if a.get("media_state") != 2)
    print(f"  Ready (media_state=2): {ready}")
    print(f"  Not ready: {pending}")

    return all_articles


# ---------------------------------------------------------------------------
# Phase 2: Crawl articles
# ---------------------------------------------------------------------------

def get_cdp_port() -> str:
    """Read CDP port from known locations."""
    for port_file in CDP_PORT_FILES:
        if port_file.exists():
            port = port_file.read_text().strip()
            if port:
                return port
    return ""


def download_raw_html_cdp(url: str, cdp_port: str) -> str | None:
    """Download article HTML via Chrome CDP (real browser TLS fingerprint)."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = subprocess.run(
                ["node", str(CDP_FETCH_SCRIPT), cdp_port, url, str(CDP_TMP_FILE)],
                capture_output=True, text=True, timeout=50,
            )
            if result.returncode != 0:
                err = result.stderr.strip()
                print(f"    CDP attempt {attempt + 1}: {err[:80]}")
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                continue

            html_text = CDP_TMP_FILE.read_text(errors="replace")

            if "环境异常" in html_text[:3000]:
                print(f"    Anti-crawl page via CDP, pausing {RATE_LIMIT_PAUSE}s...")
                time.sleep(RATE_LIMIT_PAUSE)
                continue

            if len(html_text) < 1000:
                print(f"    HTML too short ({len(html_text)} bytes), retrying...")
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                continue

            return html_text

        except subprocess.TimeoutExpired:
            print(f"    CDP timeout (attempt {attempt + 1})")
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * (2 ** attempt))
        except Exception as e:
            print(f"    CDP error: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * (2 ** attempt))

    return None


def crawl_articles(base_dir: Path, limit: int = 0, force: bool = False):
    """Download and extract articles from manifest."""
    articles = load_manifest(base_dir)
    if not articles:
        print("ERROR: No manifest found. Run --phase=list first.")
        sys.exit(1)

    articles_dir = base_dir / "articles"

    cdp_port = get_cdp_port()
    if not cdp_port:
        print("ERROR: Chrome debug not running. Start with:")
        print("  chrome_debug.sh")
        sys.exit(1)

    try:
        resp = requests.get(f"http://127.0.0.1:{cdp_port}/json/version", timeout=3)
        resp.raise_for_status()
        print(f"Chrome CDP ready on port {cdp_port}")
    except Exception:
        print(f"ERROR: Cannot reach Chrome CDP on port {cdp_port}")
        sys.exit(1)

    articles_dir.mkdir(parents=True, exist_ok=True)

    to_process = []
    for a in articles:
        if a.get("media_state") != 2:
            continue
        if not a.get("source_path"):
            continue
        if not force and a.get("status") in ("downloaded", "extracted"):
            continue
        to_process.append(a)

    if limit > 0:
        to_process = to_process[:limit]

    total = len(to_process)
    already_done = sum(
        1 for a in articles
        if a.get("status") in ("downloaded", "extracted")
    )

    print(f"Manifest: {len(articles)} total, {already_done} already done")
    print(f"To process: {total}")
    if total == 0:
        print("Nothing to do!")
        return

    img_session = requests.Session()
    stats = {"ok": 0, "failed": 0}
    start_time = time.time()

    for idx, article in enumerate(to_process):
        seq = article.get("seq", idx + 1)
        title = article.get("title", "Untitled")
        url = article["source_path"]

        print(f"\n[{idx + 1}/{total}] #{seq} {title[:40]}...")

        if idx > 0 and idx % PAUSE_EVERY == 0:
            print(f"  === Pausing {PAUSE_DURATION}s after {idx} articles ===")
            time.sleep(PAUSE_DURATION)

        raw_html = download_raw_html_cdp(url, cdp_port)
        if raw_html is None:
            print(f"  FAILED to download: {url}")
            article["status"] = "failed"
            article["errors"] = article.get("errors", []) + ["download failed"]
            stats["failed"] += 1
            save_manifest(articles, base_dir)
            continue

        try:
            result = extract_article(
                raw_html, str(articles_dir),
                seq=seq, download_img=True, session=img_session,
            )
            article["status"] = "extracted"
            article["dir_name"] = result.get("dir_name", "")
            article["author"] = result.get("author", "")
            article["publish_time"] = result.get("publish_time", "")
            if result.get("errors"):
                article["errors"] = result["errors"]
            if result.get("img_stats"):
                s = result["img_stats"]
                print(f"  OK — images: {s['ok']}/{s['total']}, "
                      f"failed: {s['failed']}, {s['bytes']} bytes")
            else:
                print(f"  OK — extracted")
            stats["ok"] += 1
        except Exception as e:
            print(f"  FAILED extraction: {e}")
            article["status"] = "failed"
            article["errors"] = article.get("errors", []) + [str(e)]
            stats["failed"] += 1

        save_manifest(articles, base_dir)

        delay = random.uniform(DELAY_MIN, DELAY_MAX)
        print(f"  Waiting {delay:.1f}s...")
        time.sleep(delay)

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"Crawl complete!")
    print(f"  Processed: {total}")
    print(f"  OK: {stats['ok']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Time: {elapsed / 60:.1f} minutes")

    failed = [a for a in articles if a.get("status") == "failed"]
    if failed:
        print(f"\nFailed articles ({len(failed)}):")
        for a in failed:
            print(f"  #{a.get('seq', '?')} {a['title'][:40]} — {a.get('errors', [])}")


# ---------------------------------------------------------------------------
# Phase: Stats
# ---------------------------------------------------------------------------

def show_stats(base_dir: Path):
    articles = load_manifest(base_dir)
    if not articles:
        print("No manifest found.")
        return

    articles_dir = base_dir / "articles"
    total = len(articles)
    by_status = {}
    for a in articles:
        s = a.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    ready = sum(1 for a in articles if a.get("media_state") == 2)

    print(f"Manifest: {base_dir / 'manifest.json'}")
    print(f"Total articles: {total}")
    print(f"Ready (media_state=2): {ready}")
    print(f"Status breakdown:")
    for status, count in sorted(by_status.items()):
        print(f"  {status}: {count}")

    if articles_dir.exists():
        total_size = sum(
            f.stat().st_size for f in articles_dir.rglob("*") if f.is_file()
        )
        print(f"\nDisk usage: {total_size / 1024 / 1024:.1f} MB")
        dir_count = sum(1 for d in articles_dir.iterdir() if d.is_dir())
        print(f"Article directories: {dir_count}")


# ---------------------------------------------------------------------------
# Phase: Retry failed
# ---------------------------------------------------------------------------

def retry_failed(base_dir: Path, limit: int = 0):
    articles = load_manifest(base_dir)
    failed = [a for a in articles if a.get("status") == "failed"]

    if not failed:
        print("No failed articles to retry.")
        return

    print(f"Found {len(failed)} failed articles. Resetting to pending...")
    for a in failed:
        a["status"] = "pending"
        a["errors"] = []
    save_manifest(articles, base_dir)

    crawl_articles(base_dir, limit=limit)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="IMA Knowledge Base Crawler")
    parser.add_argument("--phase", required=True,
                        choices=["list", "crawl", "stats", "retry"],
                        help="Phase to run")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--headers", type=str, default=None,
                        help="Path to JSON file with auth headers (for list phase)")
    parser.add_argument("--headers-json", type=str, default=None,
                        help="Auth headers as JSON string")
    parser.add_argument("--share-id", type=str, default=None,
                        help="IMA share_id (or set in config/env)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Max articles to process (0 = all)")
    parser.add_argument("--force", action="store_true",
                        help="Re-process already-done articles")

    args = parser.parse_args()

    base_dir = Path(args.output) if args.output else DEFAULT_OUTPUT_DIR
    base_dir.mkdir(parents=True, exist_ok=True)

    if args.phase == "list":
        share_id = _get_share_id(args.share_id)
        fetch_article_list(base_dir, share_id,
                           headers_file=args.headers,
                           headers_json=args.headers_json)
    elif args.phase == "crawl":
        crawl_articles(base_dir, limit=args.limit, force=args.force)
    elif args.phase == "stats":
        show_stats(base_dir)
    elif args.phase == "retry":
        retry_failed(base_dir, limit=args.limit)


if __name__ == "__main__":
    main()
