---
name: chrome-crawl
description: Crawl websites through the user's real Chrome browser with zero detection. Specialized for WeChat articles with local image download, dual HTML+Markdown output, and batch checkpoint resume.
metadata: {"openclaw":{"requires":{"bins":["node"]},"os":["darwin","linux"]}}
---

# chrome-crawl

通过用户真实 Chrome 浏览器爬取网站，零检测。专为微信公众号文章优化。

## 脚本位置

所有脚本在 Skill 目录的 `scripts/` 子目录中。用以下方式获取路径：

```bash
CRAWL_SCRIPTS="$(dirname "$(readlink -f "$(which chrome-crawl 2>/dev/null || echo "$HOME/.openclaw/workspace/skills/chrome-crawl/SKILL.md")")")/scripts"
# 或直接使用：
CRAWL_SCRIPTS="$HOME/.openclaw/workspace/skills/chrome-crawl/scripts"
```

## 启动 Chrome 调试模式

```bash
$CRAWL_SCRIPTS/chrome_debug.sh
# 输出: Chrome ready! CDP port=9222
```

## 核心原则

1. **反爬网站必须用 CDP fetch** — `curl`/`requests` 的 TLS 指纹会被检测，用 `cdp_fetch.js` 通过真实 Chrome 获取页面
2. **内容写文件，不进上下文** — 提取结果重定向到文件
3. **双格式本地保存** — HTML（人类可读）+ Markdown（AI 可读）
4. **图片必须下载到本地** — CDN 链接会过期

## 微信公众号文章

### 识别规则

- `mp.weixin.qq.com/s/...` — 微信公众号文章
- `mp.weixin.qq.com/mp/appmsgalbum?...` — 公众号合集

### 单篇抓取

```bash
CDP_PORT=$(cat ~/.chrome-crawl/cdp-port 2>/dev/null || cat ~/.openclaw/chrome-debug-port 2>/dev/null || echo 9222)

# CDP fetch（真实浏览器指纹）
node $CRAWL_SCRIPTS/cdp_fetch.js $CDP_PORT "https://mp.weixin.qq.com/s/xxx" /tmp/raw.html

# 提取：HTML + Markdown + 本地图片
python3 $CRAWL_SCRIPTS/wechat_extract.py /tmp/raw.html ./output/
```

### 批量抓取

```bash
# 从 URL 列表爬取
python3 $CRAWL_SCRIPTS/batch_crawl.py crawl urls.txt -o ./output/

# 单条 URL
python3 $CRAWL_SCRIPTS/batch_crawl.py crawl "https://mp.weixin.qq.com/s/xxx" -o ./output/

# 断点续传（中断后重新运行）
python3 $CRAWL_SCRIPTS/batch_crawl.py crawl -o ./output/

# 查看统计
python3 $CRAWL_SCRIPTS/batch_crawl.py stats -o ./output/

# 重试失败
python3 $CRAWL_SCRIPTS/batch_crawl.py retry -o ./output/

# 选项
#   --limit 10       只处理前 10 篇
#   --delay 3-8      请求间隔（秒）
#   --no-images      不下载图片
#   --force          重新处理已完成的
#   --cdp-port 9222  指定 CDP 端口
```

### wechat_extract.py 编程接口

```python
from wechat_extract import extract_article

result = extract_article(raw_html, output_dir, seq=1, download_img=True)
# result: {title, author, publish_time, html_path, md_path, img_stats, errors}
```

## 通用网页（cdp_fetch.js）

任何有反爬的网站都可以用 `cdp_fetch.js` 获取：

```bash
node $CRAWL_SCRIPTS/cdp_fetch.js $CDP_PORT "https://example.com" /tmp/page.html
# 返回 HTML 字节数到 stdout
```

## 反爬策略总结

| 方式 | TLS 指纹 | 微信检测率 |
|------|----------|-----------|
| `curl` / `requests` | Python/curl | **40%** 触发 |
| `cdp_fetch.js` (Chrome CDP) | 真实 Chrome | **0%** 触发 |

**决策规则：**
- 无反爬的页面 → `curl` 即可
- 微信/知乎/有反爬 → 必须用 `cdp_fetch.js`
- 图片 CDN 下载 → `requests` + Referer 头（CDN 不查 TLS）
- 批量 >10 篇 → `batch_crawl.py`

## 规则

1. **不要用 curl/requests 下载微信文章** — TLS 指纹会触发"环境异常"
2. **CDP 脚本写文件执行** — 不要用 `node -e "..."` 内联（shell 转义问题）
3. **每个 Chrome 标签页同时只能有一个 WebSocket 调试连接**
4. **图片下载带 Referer 头** — `Referer: https://mp.weixin.qq.com/`
5. **批量爬取先测 10 篇** — 确认质量后再全量运行

## 脚本参考

| 脚本 | 用途 |
|------|------|
| `chrome_debug.sh` | 启动调试 Chrome（同步 Cookie + 代理检测） |
| `cdp_fetch.js` | 通过 Chrome CDP 获取页面 HTML（真实 TLS 指纹） |
| `wechat_extract.py` | 微信文章提取（BeautifulSoup + 图片下载 + HTML/MD） |
| `batch_crawl.py` | 批量爬虫（CDP fetch + 断点续传 + 反爬策略） |
| `html2md.js` | 浏览器内 HTML→Markdown（通过 eval 注入） |
