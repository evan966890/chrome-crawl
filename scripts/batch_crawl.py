#!/usr/bin/env python3
"""
Batch Crawler — fetch and extract WeChat articles via Chrome CDP.

Downloads articles using a real Chrome browser (via CDP), then extracts
clean HTML + Markdown with local images using wechat_extract.

Subcommands:
  crawl   Download and extract articles from a URL list or resume from manifest
  stats   Show crawl statistics from manifest
  retry   Re-process failed articles

Usage:
  # Crawl from a URL file (one URL per line)
  python3 batch_crawl.py crawl urls.txt -o ./output/

  # Single URL
  python3 batch_crawl.py crawl "https://mp.weixin.qq.com/s/xxx" -o ./output/

  # Resume interrupted crawl (reads manifest from output dir)
  python3 batch_crawl.py crawl -o ./output/

  # With options
  python3 batch_crawl.py crawl urls.txt -o ./output/ --limit 10 --delay 3-8 --no-images

  # Show stats
  python3 batch_crawl.py stats -o ./output/

  # Retry failed articles
  python3 batch_crawl.py retry -o ./output/
"""

import argparse
import json
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
# Defaults
# ---------------------------------------------------------------------------

CDP_FETCH_SCRIPT = Path(__file__).parent / "cdp_fetch.js"
CDP_PORT_FILES = [
    Path.home() / ".chrome-crawl" / "cdp-port",
    Path.home() / ".openclaw" / "chrome-debug-port",
]
CDP_TMP_FILE = Path("/tmp/batch_cdp_fetch.html")

DEFAULT_CDP_PORT = "9222"
DEFAULT_DELAY = "2-5"

# Anti-crawl settings
PAUSE_EVERY = 200       # pause after every N articles
PAUSE_DURATION = 20     # seconds
BACKOFF_BASE = 5        # seconds (exponential: 5, 15, 45)
MAX_RETRIES = 3
RATE_LIMIT_PAUSE = 60   # seconds on anti-crawl page


# ---------------------------------------------------------------------------
# Manifest management
# ---------------------------------------------------------------------------

def load_manifest(output_dir: Path) -> list:
    """Load manifest.json from output directory."""
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return []


def save_manifest(articles: list, output_dir: Path):
    """Save manifest.json to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(articles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# URL input handling
# ---------------------------------------------------------------------------

def parse_urls(source: str) -> list[str]:
    """
    Parse URLs from a source, which can be:
    - A single URL string (starts with http)
    - A path to a text file (one URL per line)

    Returns a deduplicated list of URLs in input order.
    """
    if source.startswith("http://") or source.startswith("https://"):
        return [source.strip()]

    path = Path(source)
    if not path.exists():
        print(f"ERROR: File not found: {source}")
        sys.exit(1)

    urls = []
    seen = set()
    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if not line.startswith("http://") and not line.startswith("https://"):
                print(f"  WARNING: Skipping non-URL at line {line_num}: {line[:60]}")
                continue
            if line in seen:
                continue
            seen.add(line)
            urls.append(line)

    return urls


def build_manifest_from_urls(urls: list[str], existing: list) -> list:
    """
    Build or merge a manifest from a list of URLs.

    If an existing manifest has entries for the same URLs, their status
    is preserved (checkpoint resume). New URLs are appended as pending.
    """
    # Index existing entries by URL for fast lookup
    existing_by_url = {a["url"]: a for a in existing if a.get("url")}

    merged = []
    for idx, url in enumerate(urls):
        if url in existing_by_url:
            entry = existing_by_url[url]
            # Ensure seq is up to date
            entry["seq"] = idx + 1
            merged.append(entry)
        else:
            merged.append({
                "seq": idx + 1,
                "url": url,
                "title": "",
                "status": "pending",
                "dir_name": "",
                "errors": [],
            })

    return merged


# ---------------------------------------------------------------------------
# CDP helpers
# ---------------------------------------------------------------------------

def get_cdp_port(cli_port: str | None) -> str:
    """Determine CDP port: CLI arg > port files > default."""
    if cli_port:
        return cli_port
    for port_file in CDP_PORT_FILES:
        if port_file.exists():
            port = port_file.read_text().strip()
            if port:
                return port
    return DEFAULT_CDP_PORT


def check_chrome_ready(cdp_port: str):
    """Verify Chrome CDP is reachable. Exit if not."""
    try:
        resp = requests.get(
            f"http://127.0.0.1:{cdp_port}/json/version", timeout=5
        )
        resp.raise_for_status()
        info = resp.json()
        browser = info.get("Browser", "unknown")
        print(f"Chrome CDP ready on port {cdp_port} ({browser})")
    except requests.ConnectionError:
        print(f"ERROR: Cannot connect to Chrome CDP on port {cdp_port}")
        print("Make sure Chrome is running with --remote-debugging-port")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Chrome CDP check failed on port {cdp_port}: {e}")
        sys.exit(1)


def parse_delay(delay_str: str) -> tuple[float, float]:
    """Parse delay string like '2-5' or '3' into (min, max) floats."""
    if "-" in delay_str:
        parts = delay_str.split("-", 1)
        return float(parts[0]), float(parts[1])
    val = float(delay_str)
    return val, val


def download_raw_html_cdp(url: str, cdp_port: str) -> str | None:
    """Download page HTML via Chrome CDP (real browser TLS fingerprint)."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = subprocess.run(
                ["node", str(CDP_FETCH_SCRIPT), cdp_port, url, str(CDP_TMP_FILE)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                err = result.stderr.strip()
                print(f"    CDP attempt {attempt + 1}: {err[:120]}")
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
                continue

            html_text = CDP_TMP_FILE.read_text(errors="replace")

            # Check for WeChat anti-crawl page
            if "环境异常" in html_text[:3000]:
                print(f"    Anti-crawl page detected, pausing {RATE_LIMIT_PAUSE}s...")
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


# ---------------------------------------------------------------------------
# Subcommand: crawl
# ---------------------------------------------------------------------------

def cmd_crawl(args):
    """Download and extract articles."""
    output_dir = Path(args.output)
    articles_dir = output_dir / "articles"

    # Load existing manifest (for resume)
    existing = load_manifest(output_dir)

    # Determine URL source
    if args.source:
        urls = parse_urls(args.source)
        if not urls:
            print("ERROR: No valid URLs found in input.")
            sys.exit(1)
        articles = build_manifest_from_urls(urls, existing)
        save_manifest(articles, output_dir)
        print(f"Manifest: {len(articles)} URLs ({output_dir / 'manifest.json'})")
    elif existing:
        articles = existing
        print(f"Resuming from existing manifest: {len(articles)} URLs")
    else:
        print("ERROR: No URL source provided and no existing manifest to resume.")
        print("Usage: batch_crawl.py crawl <urls.txt|URL> -o <output_dir>")
        sys.exit(1)

    # Resolve CDP port and check readiness
    cdp_port = get_cdp_port(args.cdp_port)
    check_chrome_ready(cdp_port)

    # Parse delay
    delay_min, delay_max = parse_delay(args.delay)

    # Create articles directory
    articles_dir.mkdir(parents=True, exist_ok=True)

    # Filter articles to process
    to_process = []
    for a in articles:
        if not a.get("url"):
            continue
        if not args.force and a.get("status") in ("downloaded", "extracted"):
            continue
        to_process.append(a)

    if args.limit and args.limit > 0:
        to_process = to_process[:args.limit]

    total = len(to_process)
    already_done = sum(
        1 for a in articles
        if a.get("status") in ("downloaded", "extracted")
    )

    print(f"Total in manifest: {len(articles)}, already done: {already_done}")
    print(f"To process: {total}")
    if total == 0:
        print("Nothing to do!")
        return

    download_images = not args.no_images

    # Shared session for image downloads (images use requests, CDN is fine)
    img_session = requests.Session()

    stats = {"ok": 0, "failed": 0}
    start_time = time.time()

    for idx, article in enumerate(to_process):
        seq = article.get("seq", idx + 1)
        url = article["url"]
        title_hint = article.get("title") or url[:60]

        print(f"\n[{idx + 1}/{total}] #{seq} {title_hint}...")

        # Periodic pause
        if idx > 0 and idx % PAUSE_EVERY == 0:
            print(f"  === Pausing {PAUSE_DURATION}s after {idx} articles ===")
            time.sleep(PAUSE_DURATION)

        # Download raw HTML via Chrome CDP
        raw_html = download_raw_html_cdp(url, cdp_port)
        if raw_html is None:
            print(f"  FAILED to download: {url}")
            article["status"] = "failed"
            article["errors"] = article.get("errors", []) + ["download failed"]
            stats["failed"] += 1
            save_manifest(articles, output_dir)
            continue

        # Extract
        try:
            result = extract_article(
                raw_html, str(articles_dir),
                seq=seq, download_img=download_images, session=img_session,
            )
            article["status"] = "extracted"
            article["title"] = result.get("title", article.get("title", ""))
            article["dir_name"] = result.get("dir_name", "")
            article["author"] = result.get("author", "")
            article["publish_time"] = result.get("publish_time", "")
            if result.get("errors"):
                article["errors"] = result["errors"]
            if result.get("img_stats"):
                s = result["img_stats"]
                print(f"  OK — {result['title'][:40]} | images: {s['ok']}/{s['total']}, "
                      f"failed: {s['failed']}, {s['bytes']} bytes")
            else:
                print(f"  OK — {result['title'][:40]}")
            stats["ok"] += 1
        except Exception as e:
            print(f"  FAILED extraction: {e}")
            article["status"] = "failed"
            article["errors"] = article.get("errors", []) + [str(e)]
            stats["failed"] += 1

        # Save manifest after each article (checkpoint)
        save_manifest(articles, output_dir)

        # Random delay (skip after last article)
        if idx < total - 1:
            delay = random.uniform(delay_min, delay_max)
            print(f"  Waiting {delay:.1f}s...")
            time.sleep(delay)

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"Crawl complete!")
    print(f"  Processed: {total}")
    print(f"  OK: {stats['ok']}")
    print(f"  Failed: {stats['failed']}")
    print(f"  Time: {elapsed / 60:.1f} minutes")
    print(f"  Manifest: {output_dir / 'manifest.json'}")

    # Report failures
    failed = [a for a in articles if a.get("status") == "failed"]
    if failed:
        print(f"\nFailed articles ({len(failed)}):")
        for a in failed:
            print(f"  #{a.get('seq', '?')} {a.get('title') or a['url'][:50]} — {a.get('errors', [])}")


# ---------------------------------------------------------------------------
# Subcommand: stats
# ---------------------------------------------------------------------------

def cmd_stats(args):
    """Show crawl statistics from manifest."""
    output_dir = Path(args.output)
    articles_dir = output_dir / "articles"
    manifest_path = output_dir / "manifest.json"

    articles = load_manifest(output_dir)
    if not articles:
        print(f"No manifest found at {manifest_path}")
        return

    total = len(articles)
    by_status = {}
    for a in articles:
        s = a.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    print(f"Manifest: {manifest_path}")
    print(f"Total articles: {total}")
    print(f"Status breakdown:")
    for status, count in sorted(by_status.items()):
        pct = count / total * 100
        print(f"  {status}: {count} ({pct:.0f}%)")

    # Articles with errors
    with_errors = [a for a in articles if a.get("errors")]
    if with_errors:
        print(f"\nArticles with errors: {len(with_errors)}")
        for a in with_errors[:10]:
            print(f"  #{a.get('seq', '?')} {a.get('title') or a.get('url', '?')[:40]}")
            for err in a.get("errors", []):
                print(f"       {err}")
        if len(with_errors) > 10:
            print(f"  ... and {len(with_errors) - 10} more")

    # Disk usage
    if articles_dir.exists():
        total_size = sum(
            f.stat().st_size
            for f in articles_dir.rglob("*")
            if f.is_file()
        )
        dir_count = sum(1 for d in articles_dir.iterdir() if d.is_dir())
        print(f"\nDisk usage: {total_size / 1024 / 1024:.1f} MB")
        print(f"Article directories: {dir_count}")


# ---------------------------------------------------------------------------
# Subcommand: retry
# ---------------------------------------------------------------------------

def cmd_retry(args):
    """Re-process articles with status='failed'."""
    output_dir = Path(args.output)
    articles = load_manifest(output_dir)

    if not articles:
        print("No manifest found. Nothing to retry.")
        return

    failed = [a for a in articles if a.get("status") == "failed"]
    if not failed:
        print("No failed articles to retry.")
        return

    print(f"Found {len(failed)} failed articles. Resetting to pending...")
    for a in failed:
        a["status"] = "pending"
        a["errors"] = []
    save_manifest(articles, output_dir)

    # Reuse crawl logic
    cmd_crawl(args)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Batch Crawler — fetch and extract WeChat articles via Chrome CDP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  %(prog)s crawl urls.txt -o ./output/
  %(prog)s crawl "https://mp.weixin.qq.com/s/xxx" -o ./output/
  %(prog)s crawl -o ./output/                          # resume
  %(prog)s stats -o ./output/
  %(prog)s retry -o ./output/
""",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- crawl ---
    p_crawl = subparsers.add_parser(
        "crawl", help="Download and extract articles",
    )
    p_crawl.add_argument(
        "source", nargs="?", default=None,
        help="URL file (one URL per line) or a single URL. "
             "Omit to resume from existing manifest.",
    )
    p_crawl.add_argument(
        "-o", "--output", required=True,
        help="Output directory (manifest.json + articles/)",
    )
    p_crawl.add_argument(
        "--cdp-port", default=None,
        help=f"Chrome CDP port (default: auto-detect or {DEFAULT_CDP_PORT})",
    )
    p_crawl.add_argument(
        "--delay", default=DEFAULT_DELAY,
        help=f"Delay between articles in seconds, e.g. '2-5' or '3' (default: {DEFAULT_DELAY})",
    )
    p_crawl.add_argument(
        "--limit", type=int, default=0,
        help="Max articles to process (0 = all)",
    )
    p_crawl.add_argument(
        "--no-images", action="store_true",
        help="Skip downloading images",
    )
    p_crawl.add_argument(
        "--force", action="store_true",
        help="Re-process already-done articles",
    )
    p_crawl.set_defaults(func=cmd_crawl)

    # --- stats ---
    p_stats = subparsers.add_parser(
        "stats", help="Show crawl statistics",
    )
    p_stats.add_argument(
        "-o", "--output", required=True,
        help="Output directory containing manifest.json",
    )
    p_stats.set_defaults(func=cmd_stats)

    # --- retry ---
    p_retry = subparsers.add_parser(
        "retry", help="Retry failed articles",
    )
    p_retry.add_argument(
        "-o", "--output", required=True,
        help="Output directory containing manifest.json",
    )
    p_retry.add_argument(
        "--cdp-port", default=None,
        help=f"Chrome CDP port (default: auto-detect or {DEFAULT_CDP_PORT})",
    )
    p_retry.add_argument(
        "--delay", default=DEFAULT_DELAY,
        help=f"Delay between articles (default: {DEFAULT_DELAY})",
    )
    p_retry.add_argument(
        "--limit", type=int, default=0,
        help="Max articles to retry (0 = all)",
    )
    p_retry.add_argument(
        "--no-images", action="store_true",
        help="Skip downloading images",
    )
    p_retry.add_argument(
        "--force", action="store_true",
        help="Re-process already-done articles",
    )
    # retry needs a source=None so cmd_crawl sees it as resume
    p_retry.set_defaults(func=cmd_retry, source=None)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
