# chrome-crawl

Batch-crawl websites through your **real Chrome browser** — zero TLS fingerprint spoofing, zero detection.

Built for WeChat articles (mp.weixin.qq.com), battle-tested on 1,100 articles with **0% anti-crawl trigger rate**.

## The Problem

WeChat public account articles are notoriously hard to crawl:

- **TLS fingerprint detection** — `requests`, `curl`, `httpx` all have distinct non-browser TLS fingerprints (JA3). WeChat detects and blocks them with "环境异常" pages.
- **Image CDN expiration** — `mmbiz.qpic.cn` image URLs expire within days. If you only save HTML, images go dead.
- **Lazy-loaded content** — Images use `data-src` instead of `src`, invisible without JavaScript.
- **Hidden elements** — `visibility: hidden; opacity: 0` CSS sprinkled throughout to trip up naive extractors.

Every popular crawling tool fails at one or more of these. **chrome-crawl solves all of them.**

## How It Works

```
┌─────────────┐     CDP WebSocket      ┌──────────────────┐
│  Your Chrome │◄──────────────────────►│  cdp_fetch.js    │
│  (real TLS,  │     Page.navigate +    │  (Node.js)       │
│  real cookies,│    Runtime.evaluate    │                  │
│  real session)│                        └────────┬─────────┘
└─────────────┘                                   │ HTML
                                                  ▼
                                         ┌──────────────────┐
                                         │ wechat_extract.py │
                                         │ (BeautifulSoup)   │
                                         │                   │
                                         │ • Parse content   │
                                         │ • Download images │
                                         │ • Generate HTML   │
                                         │ • Generate MD     │
                                         └──────────────────┘
                                                  │
                                                  ▼
                                         articles/0001_标题/
                                         ├── raw.html
                                         ├── article.html
                                         ├── article.md
                                         └── assets/
                                             ├── img_001.png
                                             └── img_002.jpg
```

**Key insight:** Instead of spoofing browser fingerprints (which is an arms race), chrome-crawl uses your **actual Chrome process** via Chrome DevTools Protocol (CDP). The target server sees a real Chrome with real TLS, real cookies, and a real browsing session. There's nothing to detect.

## Comparison with Other Tools

| Feature | chrome-crawl | Scrapy | Playwright | crawl4ai | curl_cffi |
|---------|:---:|:---:|:---:|:---:|:---:|
| **Real browser TLS fingerprint** | ✅ actual Chrome | ❌ Python | ⚠️ new Chromium | ⚠️ via Playwright | ⚠️ spoofed JA3 |
| **Reuse existing cookies/sessions** | ✅ synced from Chrome | ❌ | ❌ fresh profile | ❌ | ❌ |
| **JavaScript rendering** | ✅ | ❌ | ✅ | ✅ | ❌ |
| **Anti-bot detection bypass** | ✅ undetectable | ❌ easily caught | ⚠️ `webdriver` flag | ⚠️ detectable | ⚠️ partial |
| **WeChat article support** | ✅ specialized | ❌ | ❌ | ❌ | ❌ |
| **Local image download** | ✅ automatic | ❌ manual | ❌ manual | ❌ | ❌ manual |
| **Markdown output (LLM-ready)** | ✅ | ❌ | ❌ | ✅ | ❌ |
| **Checkpoint resume** | ✅ per-article | ✅ | ❌ | ❌ | ❌ |
| **Setup complexity** | Low (Chrome + Node) | High (framework) | Medium | Low | Low |
| **Rate limit handling** | ✅ adaptive | ✅ | ❌ manual | ❌ | ❌ manual |

### vs Scrapy

Scrapy is a full-featured crawling framework — great for large-scale projects with pipelines, middleware, and item processing. But it's HTTP-only (no browser rendering), and its Python TLS fingerprint is trivially detected by modern anti-bot systems. chrome-crawl is a lightweight, single-purpose tool that trades Scrapy's extensibility for **invisible browser-based fetching**.

### vs Playwright / Puppeteer

Playwright and Puppeteer launch a **new** browser instance with a fresh profile — no cookies, no history, no extensions. They also set `navigator.webdriver = true` by default, which many sites detect. While you can patch these signals, it's a constant cat-and-mouse game. chrome-crawl sidesteps this entirely by using your **existing** Chrome process — the one you use daily, with all its organic signals.

### vs crawl4ai

crawl4ai focuses on LLM-friendly output and uses Playwright under the hood. It shares Playwright's detection issues. chrome-crawl also produces Markdown for LLMs, but additionally generates **standalone HTML** (for human review) and **downloads all images locally** (preventing CDN link expiration).

### vs curl_cffi / curl-impersonate

These libraries spoof Chrome's TLS fingerprint at the HTTP layer — clever, but they're playing catch-up with every Chrome update. They also can't execute JavaScript, render SPAs, or reuse browser sessions. chrome-crawl doesn't spoof anything — it's the real thing.

### Unique Advantages

1. **Zero spoofing, zero detection** — Uses the actual Chrome process, not a simulation. Nothing to detect because nothing is faked.
2. **Cookie inheritance** — Automatically syncs cookies from your daily Chrome. No need to export/import cookies or handle authentication manually.
3. **WeChat specialization** — Purpose-built for the specific challenges of WeChat articles: `data-src` lazy loading, hidden elements, image CDN expiration, video/audio metadata extraction.
4. **Dual-format output** — Clean HTML (human-readable) + Markdown (LLM-ready) for every article.
5. **Image preservation** — Downloads all images to local `assets/` directory with deterministic filenames. Your archive won't break when CDN links expire.
6. **Battle-tested** — 1,100 articles crawled with 0% anti-crawl trigger rate and 98.8% success rate (the 1.2% failures were non-web-page file attachments).

## Quick Start

### Prerequisites

- **Google Chrome** (your regular Chrome, with sites already logged in)
- **Node.js ≥ 22** (for native WebSocket support in CDP communication)
- **Python ≥ 3.10** with `beautifulsoup4` and `requests`

### Install

```bash
git clone https://github.com/user/chrome-crawl.git
cd chrome-crawl
./install.sh
```

### 1. Launch Debug Chrome

Close your normal Chrome first (to unlock the cookie database), then:

```bash
./scripts/chrome_debug.sh
# Output: Chrome ready! CDP port=9222 PID=12345
```

This launches Chrome with remote debugging enabled, using a separate profile that **inherits your real cookies**.

### 2. Crawl a Single Article

```bash
python3 scripts/batch_crawl.py crawl \
  "https://mp.weixin.qq.com/s/xxxxx" \
  -o ./my-articles/
```

Output:
```
Chrome CDP ready on port 9222
To process: 1

[1/1] #1 文章标题...
  OK — images: 5/5, failed: 0, 512000 bytes

Crawl complete!
  OK: 1, Failed: 0, Time: 0.1 minutes
```

### 3. Batch Crawl from URL List

Create a text file with one URL per line:

```bash
# urls.txt
https://mp.weixin.qq.com/s/aaa
https://mp.weixin.qq.com/s/bbb
https://mp.weixin.qq.com/s/ccc
# This is a comment, ignored
```

```bash
python3 scripts/batch_crawl.py crawl urls.txt -o ./output/
```

### 4. Resume Interrupted Crawl

If the crawl is interrupted (Ctrl+C, network failure, etc.), just re-run the same command. It reads `manifest.json` from the output directory and **skips already-completed articles**.

```bash
# Resumes from where it left off
python3 scripts/batch_crawl.py crawl -o ./output/
```

### 5. Check Progress

```bash
python3 scripts/batch_crawl.py stats -o ./output/
```

### 6. Retry Failed Articles

```bash
python3 scripts/batch_crawl.py retry -o ./output/
```

## Output Structure

```
output/
├── manifest.json              # Article metadata + crawl status
└── articles/
    ├── 0001_文章标题/
    │   ├── raw.html           # Original page HTML
    │   ├── article.html       # Clean, self-contained HTML
    │   ├── article.md         # Markdown (for LLMs/search)
    │   └── assets/            # Local images
    │       ├── img_001_a1b2c3d4.png
    │       └── img_002_e5f6a7b8.jpg
    ├── 0002_另一篇文章/
    │   └── ...
    └── ...
```

### manifest.json

Each article entry:

```json
{
  "seq": 1,
  "url": "https://mp.weixin.qq.com/s/xxx",
  "title": "文章标题",
  "status": "extracted",
  "dir_name": "0001_文章标题",
  "author": "作者名",
  "publish_time": "2025-01-01",
  "errors": []
}
```

Status values: `pending` → `extracted` | `failed`

## CLI Reference

```
python3 batch_crawl.py <command> [source] [options]

Commands:
  crawl [source]    Crawl articles. Source can be:
                    - A URL (starts with http)
                    - A text file (one URL per line)
                    - Omitted (resume from manifest.json in output dir)
  stats             Show crawl statistics
  retry             Re-process failed articles

Options:
  -o, --output DIR  Output directory (required)
  --cdp-port PORT   Chrome CDP port (default: auto-detect or 9222)
  --delay MIN-MAX   Delay between articles in seconds (default: 2-5)
  --limit N         Max articles to process (0 = all)
  --no-images       Skip image downloads
  --force           Re-process already-extracted articles
```

## Anti-Crawl Strategy

Built-in protections (all automatic, no configuration needed):

| Strategy | Detail |
|----------|--------|
| **Real browser TLS** | Pages fetched through actual Chrome — identical to manual browsing |
| **Random delay** | 2-5 seconds between articles (configurable via `--delay`) |
| **Exponential backoff** | Failed requests retry with 5s → 10s → 20s delay |
| **Anti-crawl detection** | Detects "环境异常" pages, auto-pauses 60 seconds |
| **Periodic pause** | 20-second break every 200 articles |
| **Checkpoint resume** | Manifest saved after every article — interrupt anytime |
| **Image CDN handling** | Images downloaded with `Referer: mp.weixin.qq.com` header |

## Advanced: Extract Without Crawling

Use `wechat_extract.py` directly if you already have the HTML:

```bash
# CLI
python3 scripts/wechat_extract.py page.html ./output/

# Python API
from wechat_extract import extract_article

result = extract_article(
    raw_html,              # Full HTML string
    "./output/",           # Output directory
    seq=1,                 # Sequence number prefix
    download_img=True,     # Download images locally
)
# result = {title, author, publish_time, html_path, md_path, img_stats, errors}
```

## Advanced: CDP Fetch for Any Website

`cdp_fetch.js` is a general-purpose tool — use it for any website that blocks non-browser HTTP clients:

```bash
# Fetch any page through your Chrome
node scripts/cdp_fetch.js 9222 "https://example.com" /tmp/page.html
```

## Advanced: Upload to Feishu (Lark)

Upload extracted articles (with images) to Feishu documents:

```bash
# Upload a markdown file with local images
python3 scripts/feishu_upload.py article.md assets/
```

Credentials are loaded from `~/.chrome-crawl/config.json` (not committed to git):

```json
{"feishu": {"app_id": "...", "app_secret": "..."}}
```

Or set environment variables: `FEISHU_APP_ID`, `FEISHU_APP_SECRET`.

**Image upload uses a 3-step process:** create empty image block → upload media file → PATCH with `replace_image` to link the token. This is handled automatically by the script.

## How We Tested

| Metric | Result |
|--------|--------|
| Articles crawled | 1,100 |
| Success rate | 98.8% (13 failures were non-web attachments) |
| Anti-crawl triggers | **0** |
| Total time | 144 minutes |
| Total disk usage | 4.75 GB (with images) |
| Images downloaded | ~6,000 |
| Image failure rate | < 0.1% |

## Requirements

- macOS or Linux
- Google Chrome
- Node.js ≥ 22
- Python ≥ 3.10

## License

MIT
