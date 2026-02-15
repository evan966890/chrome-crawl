#!/usr/bin/env python3
"""
Extract WeChat article content to clean HTML and Markdown.

Features:
- BeautifulSoup-based HTML parsing (replaces fragile regex)
- Image download to local assets/ directory
- Cleans visibility:hidden / opacity:0 styles
- Video/audio metadata extraction
- Robust error handling

Usage:
  CLI:  python3 wechat_extract.py input.html output_dir/
  API:  from wechat_extract import extract_article
        result = extract_article(raw_html, output_dir, seq=1)
"""

import sys
import re
import html
import hashlib
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Comment

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IMG_HEADERS = {
    "Referer": "https://mp.weixin.qq.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

IMG_TIMEOUT = 30  # seconds per image download
IMG_RETRY = 2

# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def extract_title(raw_html: str) -> str:
    m = re.search(r"var msg_title = [\"'](.+?)[\"']", raw_html)
    if m:
        title = m.group(1).split("'")[0].split('"')[0]
        return html.unescape(title).strip()
    soup = BeautifulSoup(raw_html, "html.parser")
    h1 = soup.select_one('h1.rich_media_title')
    if h1:
        return h1.get_text(strip=True)
    return "Untitled"


def extract_author(raw_html: str) -> str:
    m = re.search(r"var nickname = [\"'](.+?)[\"']", raw_html)
    if m:
        return html.unescape(m.group(1)).strip()
    # Fallback: try profile_nickname span
    soup = BeautifulSoup(raw_html, "html.parser")
    nick = soup.select_one('#js_name, .rich_media_meta_nickname .rich_media_meta_link')
    if nick:
        return nick.get_text(strip=True)
    return ""


def extract_publish_time(raw_html: str) -> str:
    m = re.search(r"var ct\s*=\s*[\"'](\d+)[\"']", raw_html)
    if m:
        ts = int(m.group(1))
        return time.strftime("%Y-%m-%d", time.localtime(ts))
    return ""


def extract_source_url(raw_html: str) -> str:
    m = re.search(r"var msg_source_url = '(https?://[^']+)'", raw_html)
    if m:
        return m.group(1)
    return ""


# ---------------------------------------------------------------------------
# Content extraction (BeautifulSoup)
# ---------------------------------------------------------------------------

def _remove_hidden_elements(soup: BeautifulSoup) -> None:
    """Remove elements with visibility:hidden or opacity:0 inline styles."""
    for tag in soup.find_all(style=True):
        style = tag.get("style", "")
        if re.search(r"visibility\s*:\s*hidden", style) or \
           re.search(r"opacity\s*:\s*0(?:[;\s]|$)", style) or \
           re.search(r"display\s*:\s*none", style):
            tag.decompose()


def _remove_unwanted_tags(soup: BeautifulSoup) -> None:
    """Remove script, style, link, meta, comments, and mpvoice/mpvideo placeholders."""
    for tag in soup.find_all(["script", "style", "link", "meta", "noscript", "iframe"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()


def _fix_images(soup: BeautifulSoup) -> None:
    """Replace data-src with src for WeChat lazy-loaded images."""
    for img in soup.find_all("img"):
        data_src = img.get("data-src")
        if data_src:
            img["src"] = data_src
            del img["data-src"]
        # Remove data-* clutter
        for attr in list(img.attrs):
            if attr.startswith("data-") and attr != "data-src":
                del img[attr]


def _make_placeholder(soup: BeautifulSoup, text: str, css_class: str):
    """Create a placeholder <p> tag."""
    p = soup.new_tag("p")
    p.string = text
    p["class"] = css_class
    return p


def _extract_video_info(content, soup: BeautifulSoup) -> list:
    """Extract video metadata from mpvideo tags."""
    videos = []
    for v in content.find_all(attrs={"class": re.compile(r"video_iframe|mpvideo")}):
        vid_title = v.get("data-title", "").strip()
        vid_src = v.get("data-src", v.get("src", "")).strip()
        videos.append({"title": vid_title or "未命名视频", "src": vid_src})
        v.replace_with(
            _make_placeholder(soup, f"[视频: {vid_title or '未命名视频'}]", "video-placeholder")
        )
    return videos


def _extract_audio_info(content, soup: BeautifulSoup) -> list:
    """Extract audio metadata from mpvoice tags."""
    audios = []
    for a in content.find_all(attrs={"class": re.compile(r"audio_iframe|mpvoice")}):
        aud_name = a.get("name", a.get("data-title", "")).strip()
        audios.append({"name": aud_name or "未命名音频"})
        a.replace_with(
            _make_placeholder(soup, f"[音频: {aud_name or '未命名音频'}]", "audio-placeholder")
        )
    # Also handle <mpvoice> custom tags
    for a in content.find_all("mpvoice"):
        aud_name = a.get("name", "").strip()
        audios.append({"name": aud_name or "未命名音频"})
        a.replace_with(
            _make_placeholder(soup, f"[音频: {aud_name or '未命名音频'}]", "audio-placeholder")
        )
    return audios


def extract_content_soup(raw_html: str) -> BeautifulSoup:
    """Parse raw HTML and return a cleaned BeautifulSoup of #js_content."""
    soup = BeautifulSoup(raw_html, "html.parser")
    content_div = soup.find(id="js_content")
    if not content_div:
        # Fallback: try rich_media_content
        content_div = soup.select_one('.rich_media_content')
    if not content_div:
        return BeautifulSoup("", "html.parser")

    _remove_unwanted_tags(content_div)
    _remove_hidden_elements(content_div)
    _fix_images(content_div)
    _extract_video_info(content_div, soup)
    _extract_audio_info(content_div, soup)

    return content_div


# ---------------------------------------------------------------------------
# Image download
# ---------------------------------------------------------------------------

def _img_ext(url: str, content_type: str = "") -> str:
    """Determine image file extension from URL or Content-Type."""
    if content_type:
        ct = content_type.lower()
        if "png" in ct:
            return ".png"
        if "gif" in ct:
            return ".gif"
        if "webp" in ct:
            return ".webp"
        if "svg" in ct:
            return ".svg"
        if "jpeg" in ct or "jpg" in ct:
            return ".jpg"
    # Guess from URL
    path = urlparse(url).path.lower()
    for ext in (".png", ".gif", ".webp", ".svg", ".jpg", ".jpeg"):
        if ext in path:
            return ext
    # WeChat mmbiz default
    fmt = re.search(r"wx_fmt=(\w+)", url)
    if fmt:
        f = fmt.group(1).lower()
        return f".{f}" if f != "jpeg" else ".jpg"
    return ".jpg"


def download_images(content_soup: BeautifulSoup, assets_dir: Path,
                    session: requests.Session = None) -> dict:
    """Download all images in content_soup to assets_dir, return stats."""
    assets_dir.mkdir(parents=True, exist_ok=True)
    sess = session or requests.Session()

    stats = {"total": 0, "ok": 0, "failed": 0, "skipped": 0, "bytes": 0}
    img_counter = 0

    for img in content_soup.find_all("img"):
        src = img.get("src", "")
        if not src or not src.startswith("http"):
            continue

        stats["total"] += 1
        img_counter += 1

        # Generate deterministic filename
        url_hash = hashlib.md5(src.encode()).hexdigest()[:8]
        ext = _img_ext(src)
        filename = f"img_{img_counter:03d}_{url_hash}{ext}"
        filepath = assets_dir / filename

        # Skip if already downloaded
        if filepath.exists() and filepath.stat().st_size > 0:
            img["src"] = f"assets/{filename}"
            stats["skipped"] += 1
            stats["ok"] += 1
            continue

        # Download with retry
        ok = False
        for attempt in range(IMG_RETRY + 1):
            try:
                resp = sess.get(src, headers=IMG_HEADERS, timeout=IMG_TIMEOUT,
                                stream=True)
                resp.raise_for_status()
                data = resp.content
                if len(data) < 100:
                    # Likely an error page, not a real image
                    raise ValueError(f"Image too small ({len(data)} bytes)")
                filepath.write_bytes(data)
                img["src"] = f"assets/{filename}"
                stats["ok"] += 1
                stats["bytes"] += len(data)
                ok = True
                break
            except Exception:
                if attempt < IMG_RETRY:
                    time.sleep(1 * (attempt + 1))
                continue

        if not ok:
            stats["failed"] += 1
            # Keep original URL as fallback
            img["src"] = src

    return stats


# ---------------------------------------------------------------------------
# Build clean HTML
# ---------------------------------------------------------------------------

def build_clean_html(title: str, author: str, source_url: str,
                     publish_time: str, content_html: str) -> str:
    meta_parts = []
    if author:
        meta_parts.append(f"作者: {html.escape(author)}")
    if publish_time:
        meta_parts.append(f"发布: {html.escape(publish_time)}")
    if source_url:
        meta_parts.append(
            f'来源: <a href="{html.escape(source_url)}">{html.escape(source_url)}</a>'
        )
    meta_html = "<br>\n  ".join(meta_parts)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="author" content="{html.escape(author)}">
<meta name="source-url" content="{html.escape(source_url)}">
<style>
body {{
  max-width: 680px;
  margin: 40px auto;
  padding: 0 20px;
  font-family: -apple-system, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  line-height: 1.8;
  color: #333;
  background: #fff;
}}
h1 {{ font-size: 1.6em; line-height: 1.4; margin-bottom: 0.5em; }}
.meta {{ color: #999; font-size: 0.9em; margin-bottom: 2em; border-bottom: 1px solid #eee; padding-bottom: 1em; }}
img {{ max-width: 100%; height: auto; display: block; margin: 1em auto; border-radius: 4px; }}
p {{ margin: 0.8em 0; }}
section {{ margin: 0; padding: 0; }}
blockquote {{ border-left: 3px solid #ddd; margin: 1em 0; padding: 0.5em 1em; color: #666; }}
pre, code {{ background: #f5f5f5; border-radius: 3px; font-size: 0.9em; }}
pre {{ padding: 1em; overflow-x: auto; }}
code {{ padding: 2px 4px; }}
a {{ color: #576b95; text-decoration: none; }}
.video-placeholder, .audio-placeholder {{ background: #f0f0f0; padding: 12px; border-radius: 6px; text-align: center; color: #666; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<div class="meta">
  {meta_html}
</div>
{content_html}
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTML to Markdown conversion
# ---------------------------------------------------------------------------

def _soup_to_markdown(soup) -> str:
    """Convert BeautifulSoup element to Markdown recursively."""
    parts = []

    for child in soup.children:
        if isinstance(child, str):
            text = child
            # Collapse whitespace but preserve newlines
            text = re.sub(r'[ \t]+', ' ', text)
            parts.append(text)
            continue

        if not hasattr(child, 'name'):
            continue

        tag = child.name

        if tag in ('script', 'style', 'noscript'):
            continue

        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(tag[1])
            text = child.get_text(strip=True)
            if text:
                parts.append(f"\n\n{'#' * level} {text}\n\n")

        elif tag in ('strong', 'b'):
            text = _soup_to_markdown(child).strip()
            if text:
                parts.append(f"**{text}**")

        elif tag in ('em', 'i'):
            text = _soup_to_markdown(child).strip()
            if text:
                parts.append(f"*{text}*")

        elif tag == 'img':
            src = child.get('src', '')
            alt = child.get('alt', '')
            if src:
                parts.append(f"\n\n![{alt}]({src})\n\n")

        elif tag == 'a':
            href = child.get('href', '')
            text = child.get_text(strip=True)
            if text and href and not href.startswith('javascript:'):
                parts.append(f"[{text}]({href})")
            elif text:
                parts.append(text)

        elif tag == 'br':
            parts.append("\n")

        elif tag == 'hr':
            parts.append("\n\n---\n\n")

        elif tag == 'p':
            text = _soup_to_markdown(child).strip()
            if text:
                parts.append(f"\n\n{text}\n\n")

        elif tag == 'blockquote':
            text = _soup_to_markdown(child).strip()
            if text:
                quoted = '\n'.join(f"> {line}" for line in text.split('\n'))
                parts.append(f"\n\n{quoted}\n\n")

        elif tag == 'pre':
            code = child.find('code')
            text = (code or child).get_text()
            lang = ''
            if code and code.get('class'):
                for cls in code['class']:
                    m = re.match(r'language-(\w+)', cls)
                    if m:
                        lang = m.group(1)
                        break
            parts.append(f"\n\n```{lang}\n{text}\n```\n\n")

        elif tag == 'code':
            text = child.get_text()
            parts.append(f"`{text}`")

        elif tag in ('ul', 'ol'):
            items = child.find_all('li', recursive=False)
            list_parts = []
            for idx, li in enumerate(items):
                text = _soup_to_markdown(li).strip()
                if text:
                    prefix = f"{idx + 1}. " if tag == 'ol' else "- "
                    list_parts.append(f"{prefix}{text}")
            if list_parts:
                parts.append("\n\n" + "\n".join(list_parts) + "\n\n")

        elif tag == 'table':
            rows = child.find_all('tr')
            if rows:
                table_data = []
                for tr in rows:
                    cells = tr.find_all(['td', 'th'])
                    row = [c.get_text(strip=True).replace('|', '\\|') for c in cells]
                    table_data.append(row)
                if table_data:
                    col_count = max(len(r) for r in table_data)
                    for r in table_data:
                        while len(r) < col_count:
                            r.append('')
                    header = "| " + " | ".join(table_data[0]) + " |"
                    sep = "| " + " | ".join(["---"] * col_count) + " |"
                    body = "\n".join(
                        "| " + " | ".join(r) + " |" for r in table_data[1:]
                    )
                    parts.append(f"\n\n{header}\n{sep}\n{body}\n\n")

        else:
            # div, section, span, etc. — recurse
            parts.append(_soup_to_markdown(child))

    return ''.join(parts)


def html_to_markdown(content_soup, title: str = "", author: str = "",
                     source_url: str = "", publish_time: str = "") -> str:
    """Convert BeautifulSoup content to Markdown string."""
    md = _soup_to_markdown(content_soup)

    # Clean up whitespace
    md = re.sub(r'\n{3,}', '\n\n', md)
    md = re.sub(r'[ \t]+\n', '\n', md)
    md = md.strip()

    # Build header
    header = f"# {title}\n\n"
    meta_parts = []
    if author:
        meta_parts.append(f"作者: {author}")
    if publish_time:
        meta_parts.append(f"发布: {publish_time}")
    if source_url:
        meta_parts.append(f"来源: {source_url}")
    if meta_parts:
        header += "\n".join(meta_parts) + "\n"
    header += "\n---\n\n"

    return header + md


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------

def safe_dirname(title: str, seq: int = 0) -> str:
    """Generate a filesystem-safe directory name with optional sequence prefix."""
    safe = re.sub(r'[^\w\u4e00-\u9fff-]', '_', title)[:50].rstrip('_')
    if not safe:
        safe = "untitled"
    if seq > 0:
        return f"{seq:04d}_{safe}"
    return safe


def extract_article(raw_html: str, output_dir: str | Path,
                    seq: int = 0, download_img: bool = True,
                    session: requests.Session = None) -> dict:
    """
    Extract a WeChat article from raw HTML.

    Args:
        raw_html: Full page HTML string
        output_dir: Base directory to write output into
        seq: Sequence number for directory prefix (0 = no prefix)
        download_img: Whether to download images locally
        session: Optional requests.Session for connection reuse

    Returns:
        dict with keys: title, author, publish_time, source_url,
                        dir_name, html_path, md_path, img_stats, errors
    """
    result = {
        "title": "", "author": "", "publish_time": "", "source_url": "",
        "dir_name": "", "html_path": "", "md_path": "",
        "img_stats": {}, "errors": [],
    }

    try:
        title = extract_title(raw_html)
        author = extract_author(raw_html)
        publish_time = extract_publish_time(raw_html)
        source_url = extract_source_url(raw_html)
    except Exception as e:
        result["errors"].append(f"metadata extraction: {e}")
        title = "Untitled"
        author = ""
        publish_time = ""
        source_url = ""

    result["title"] = title
    result["author"] = author
    result["publish_time"] = publish_time
    result["source_url"] = source_url

    # Parse content
    try:
        content_soup = extract_content_soup(raw_html)
    except Exception as e:
        result["errors"].append(f"content extraction: {e}")
        return result

    # Prepare output directory
    dir_name = safe_dirname(title, seq)
    result["dir_name"] = dir_name
    base = Path(output_dir)
    article_dir = base / dir_name
    article_dir.mkdir(parents=True, exist_ok=True)

    # Save raw.html
    try:
        (article_dir / "raw.html").write_text(raw_html, encoding="utf-8")
    except Exception as e:
        result["errors"].append(f"save raw.html: {e}")

    # Download images
    if download_img:
        try:
            assets_dir = article_dir / "assets"
            img_stats = download_images(content_soup, assets_dir, session=session)
            result["img_stats"] = img_stats
        except Exception as e:
            result["errors"].append(f"image download: {e}")

    # Build clean HTML
    try:
        content_html_str = str(content_soup)
        clean_html = build_clean_html(title, author, source_url,
                                      publish_time, content_html_str)
        html_path = article_dir / "article.html"
        html_path.write_text(clean_html, encoding="utf-8")
        result["html_path"] = str(html_path)
    except Exception as e:
        result["errors"].append(f"build HTML: {e}")

    # Convert to Markdown
    try:
        md_content = html_to_markdown(content_soup, title, author,
                                      source_url, publish_time)
        md_path = article_dir / "article.md"
        md_path.write_text(md_content, encoding="utf-8")
        result["md_path"] = str(md_path)
    except Exception as e:
        result["errors"].append(f"build Markdown: {e}")

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 wechat_extract.py input.html output_dir/ [seq]")
        print("  seq: optional sequence number (e.g., 1 → 0001_ prefix)")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    seq = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    raw_html = input_path.read_text(errors='replace')

    result = extract_article(raw_html, output_dir, seq=seq, download_img=True)

    print(f"Title: {result['title']}")
    print(f"Author: {result['author']}")
    print(f"Published: {result['publish_time']}")
    if result['html_path']:
        size = Path(result['html_path']).stat().st_size
        print(f"HTML: {result['html_path']} ({size} bytes)")
    if result['md_path']:
        size = Path(result['md_path']).stat().st_size
        print(f"Markdown: {result['md_path']} ({size} bytes)")
    if result['img_stats']:
        s = result['img_stats']
        print(f"Images: {s['ok']}/{s['total']} OK, {s['failed']} failed, "
              f"{s['skipped']} skipped, {s['bytes']} bytes total")
    if result['errors']:
        print(f"Errors: {result['errors']}")


if __name__ == "__main__":
    main()
