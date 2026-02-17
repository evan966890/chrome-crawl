#!/usr/bin/env python3
"""Upload articles to Feishu (Lark) as documents with images.

Credentials are loaded from (in priority order):
  1. Environment variables: FEISHU_APP_ID, FEISHU_APP_SECRET
  2. Config file: ~/.chrome-crawl/config.json  {"feishu": {"app_id": "...", "app_secret": "..."}}

Usage:
  # Upload a single markdown file with images
  python3 feishu_upload.py <md_file> [assets_dir]

  # Python API
  from feishu_upload import get_token, upload_article
  token = get_token()
  result = upload_article(token, "Title", Path("article.md"), Path("assets/"))
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://open.feishu.cn/open-apis"

CONFIG_PATHS = [
    Path.home() / ".chrome-crawl" / "config.json",
]


def _load_config() -> dict:
    for p in CONFIG_PATHS:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _get_feishu_credentials() -> tuple[str, str]:
    """Get Feishu app credentials from env vars or config file."""
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if app_id and app_secret:
        return app_id, app_secret

    config = _load_config()
    feishu = config.get("feishu", {})
    app_id = feishu.get("app_id")
    app_secret = feishu.get("app_secret")
    if app_id and app_secret:
        return app_id, app_secret

    raise RuntimeError(
        "Feishu credentials not found. Either:\n"
        "  1. Set FEISHU_APP_ID and FEISHU_APP_SECRET environment variables, or\n"
        "  2. Add to ~/.chrome-crawl/config.json:\n"
        '     {"feishu": {"app_id": "...", "app_secret": "..."}}'
    )


def get_token() -> str:
    """Get Feishu tenant access token."""
    app_id, app_secret = _get_feishu_credentials()
    resp = requests.post(f"{BASE_URL}/auth/v3/tenant_access_token/internal", json={
        "app_id": app_id, "app_secret": app_secret,
    })
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Token error: {data}")
    return data["tenant_access_token"]


def create_document(token: str, title: str) -> tuple[str, str]:
    resp = requests.post(
        f"{BASE_URL}/docx/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": title, "folder_token": ""},
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Create doc error: {data}")
    doc = data["data"]["document"]
    doc_id = doc["document_id"]
    return doc_id, f"https://feishu.cn/docx/{doc_id}"


def api_post(token, url, payload, retries=3):
    """POST with rate-limit retry."""
    for i in range(retries):
        resp = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)
        if resp.status_code == 429:
            time.sleep(2 * (i + 1))
            continue
        return resp
    return resp


def upload_image(token: str, img_path: Path, doc_id: str, block_id: str) -> bool:
    """Upload image to a Feishu image block and link it. Returns True on success.

    Three-step process:
      1. Upload file to drive media (already have block from caller)
      2. PATCH block with replace_image to link the file_token
    Note: Use replace_image, NOT update_image (the latter returns invalid param).
    """
    for attempt in range(3):
        try:
            # Step 1: Upload file
            with open(img_path, "rb") as f:
                resp = requests.post(
                    f"{BASE_URL}/drive/v1/medias/upload_all",
                    headers={"Authorization": f"Bearer {token}"},
                    data={
                        "file_name": img_path.name,
                        "parent_type": "docx_image",
                        "parent_node": block_id,
                        "size": str(img_path.stat().st_size),
                    },
                    files={"file": (img_path.name, f)},
                )
            if resp.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            data = resp.json()
            if data.get("code") != 0:
                return False
            file_token = data["data"]["file_token"]

            # Step 2: Link token to block via replace_image
            resp2 = requests.patch(
                f"{BASE_URL}/docx/v1/documents/{doc_id}/blocks/{block_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"replace_image": {"token": file_token}},
            )
            if resp2.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            return resp2.status_code == 200 and resp2.json().get("code") == 0

        except Exception:
            time.sleep(1)
    return False


def parse_md_with_images(md_content: str, assets_dir: Path) -> list:
    """Parse markdown into a list of (type, data) tuples.

    Types: 'blocks' (list of Feishu blocks), 'image' (Path to local image file)
    """
    items = []
    current_blocks = []
    lines = md_content.split("\n")
    i = 0

    def flush():
        nonlocal current_blocks
        if current_blocks:
            items.append(("blocks", current_blocks))
            current_blocks = []

    while i < len(lines):
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        # Code block
        if line.strip().startswith("```"):
            lang = line.strip().lstrip("`").strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1
            code_text = "\n".join(code_lines)
            if code_text.strip():
                current_blocks.append({
                    "block_type": 14,
                    "code": {
                        "style": {},
                        "elements": [{"text_run": {"content": code_text}}],
                        "language": _map_language(lang),
                    }
                })
            continue

        # Heading
        m = re.match(r'^(#{1,6})\s+(.+)$', line)
        if m:
            level = min(len(m.group(1)), 3)
            text = m.group(2).strip()
            bt = level + 2
            key = {3: "heading1", 4: "heading2", 5: "heading3"}[bt]
            current_blocks.append({
                "block_type": bt,
                key: {"style": {}, "elements": [{"text_run": {"content": text}}]},
            })
            i += 1
            continue

        # HR
        if re.match(r'^[-*_]{3,}\s*$', line):
            current_blocks.append({"block_type": 22, "divider": {}})
            i += 1
            continue

        # Blockquote
        if line.startswith("> "):
            qt = line[2:].strip()
            while i + 1 < len(lines) and lines[i + 1].startswith("> "):
                i += 1
                qt += "\n" + lines[i][2:].strip()
            current_blocks.append(_text_block(f"> {qt}"))
            i += 1
            continue

        # Bullet list
        if re.match(r'^[-*+]\s+', line):
            text = re.sub(r'^[-*+]\s+', '', line).strip()
            current_blocks.append({
                "block_type": 16,
                "bullet": {"style": {}, "elements": [{"text_run": {"content": text}}]},
            })
            i += 1
            continue

        # Ordered list
        m = re.match(r'^\d+\.\s+(.+)$', line)
        if m:
            text = m.group(1).strip()
            current_blocks.append({
                "block_type": 17,
                "ordered": {"style": {}, "elements": [{"text_run": {"content": text}}]},
            })
            i += 1
            continue

        # Image
        m = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', line)
        if m:
            src = m.group(2)
            # Check if it's a local image
            local_path = assets_dir / src if not os.path.isabs(src) else Path(src)
            if not local_path.exists() and src.startswith("assets/"):
                local_path = assets_dir.parent / src
            if local_path.exists() and local_path.stat().st_size > 0:
                flush()
                items.append(("image", local_path))
            else:
                current_blocks.append(_text_block(f"[{m.group(1) or 'image'}]"))
            i += 1
            continue

        # Regular paragraph
        current_blocks.append(_text_block(line))
        i += 1

    flush()
    return items


def _text_block(text: str) -> dict:
    return {
        "block_type": 2,
        "text": {"style": {}, "elements": [{"text_run": {"content": text or " "}}]},
    }


def _map_language(lang: str) -> int:
    m = {
        "python": 49, "py": 49, "javascript": 36, "js": 36,
        "typescript": 73, "ts": 73, "bash": 7, "sh": 7, "shell": 7,
        "json": 38, "html": 32, "css": 16, "java": 35, "go": 29,
        "rust": 56, "sql": 62, "yaml": 78, "yml": 78, "": 0,
    }
    return m.get(lang.lower(), 0)


def write_items(token: str, doc_id: str, items: list) -> dict:
    """Write text blocks and images to document."""
    stats = {"blocks_ok": 0, "blocks_total": 0, "imgs_ok": 0, "imgs_total": 0}

    for item_type, data in items:
        if item_type == "blocks":
            stats["blocks_total"] += len(data)
            # Write in batches of 30
            for bi in range(0, len(data), 30):
                batch = data[bi:bi + 30]
                resp = api_post(token,
                    f"{BASE_URL}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children",
                    {"children": batch, "index": -1})

                if resp.status_code == 200 and resp.json().get("code") == 0:
                    stats["blocks_ok"] += len(batch)
                else:
                    # One by one fallback
                    for block in batch:
                        r = api_post(token,
                            f"{BASE_URL}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children",
                            {"children": [block], "index": -1})
                        if r.status_code == 200 and r.json().get("code") == 0:
                            stats["blocks_ok"] += 1
                        time.sleep(0.3)
                time.sleep(0.5)

        elif item_type == "image":
            img_path = data
            stats["imgs_total"] += 1

            # Step 1: create empty image block
            resp = api_post(token,
                f"{BASE_URL}/docx/v1/documents/{doc_id}/blocks/{doc_id}/children",
                {"children": [{"block_type": 27, "image": {}}], "index": -1})

            if resp.status_code != 200 or resp.json().get("code") != 0:
                continue

            block_id = resp.json()["data"]["children"][0]["block_id"]

            # Step 2: upload image and link to block
            ok = upload_image(token, img_path, doc_id, block_id)
            if ok:
                stats["imgs_ok"] += 1
            time.sleep(0.5)

    return stats


def upload_article(token: str, title: str, md_path: Path, assets_dir: Path) -> dict:
    """Upload a markdown article with images to Feishu.

    Returns: {doc_id, url, blocks_ok, blocks_total, imgs_ok, imgs_total}
    """
    doc_id, url = create_document(token, title)
    md_content = md_path.read_text(encoding="utf-8")
    items = parse_md_with_images(md_content, assets_dir)
    stats = write_items(token, doc_id, items)
    return {"doc_id": doc_id, "url": url, **stats}


def main():
    if len(sys.argv) < 2:
        print("Usage: feishu_upload.py <markdown_file> [assets_dir]")
        print("  Upload a markdown file (with local images) to a Feishu document.")
        sys.exit(1)

    md_path = Path(sys.argv[1])
    if not md_path.exists():
        print(f"ERROR: File not found: {md_path}")
        sys.exit(1)

    assets_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else md_path.parent / "assets"
    title = md_path.stem

    # Try to extract title from first markdown heading
    content = md_path.read_text(encoding="utf-8")
    m = re.match(r'^#\s+(.+)$', content, re.MULTILINE)
    if m:
        title = m.group(1).strip()

    print("Getting Feishu token...")
    token = get_token()
    print(f"Uploading: {title}")

    result = upload_article(token, title, md_path, assets_dir)
    print(f"OK — {result['url']}")
    print(f"     blocks: {result['blocks_ok']}/{result['blocks_total']}, "
          f"images: {result['imgs_ok']}/{result['imgs_total']}")


if __name__ == "__main__":
    main()
