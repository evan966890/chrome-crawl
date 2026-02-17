---
name: chrome-crawl
description: Crawl websites through the user's real Chrome browser with zero detection. Specialized for WeChat articles with local image download, dual HTML+Markdown output, batch checkpoint resume, and Feishu document upload with images.
metadata: {"openclaw":{"requires":{"bins":["node"]},"os":["darwin","linux"]}}
---

# Chrome Crawl

通过用户真实 Chrome 浏览器爬取网站，零检测。专为微信公众号文章优化，支持飞书文档上传。

## 启动

```bash
# 方式 1：使用本 skill 自带脚本
CRAWL_SCRIPTS="$(dirname "$(readlink -f "$0")")/scripts"
$CRAWL_SCRIPTS/chrome_debug.sh

# 方式 2：如果有 agent-browser
CDP_PORT=$(cat ~/.chrome-crawl/cdp-port 2>/dev/null)
curl -s "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null 2>&1 || $CRAWL_SCRIPTS/chrome_debug.sh
CDP_PORT=$(cat ~/.chrome-crawl/cdp-port)
```

## 打开页面（需要 agent-browser）

```bash
agent-browser --cdp $CDP_PORT open "https://example.com"
agent-browser --cdp $CDP_PORT wait --load networkidle
```

---

## 核心原则

1. **内容写文件，不进上下文** — 所有提取的页面内容必须重定向到文件，你的上下文中只保留进度元数据
2. **双格式本地保存** — 每次提取都保存 HTML（人类可读）和 Markdown（AI 可读）两份
3. **上传飞书文档** — 提取完成后用 `feishu_upload.py` 上传飞书文档（含图片）
4. **只回复链接** — 回复给用户的消息中只包含飞书文档链接，不要贴内容

---

## 私密配置

Feishu 凭证、IMA share_id 等私密信息存放在本地配置文件中，**不进 Git**：

```json
// ~/.chrome-crawl/config.json
{
  "feishu": {
    "app_id": "your_app_id",
    "app_secret": "your_app_secret"
  },
  "ima": {
    "share_id": "your_share_id"
  }
}
```

也可以通过环境变量设置：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`IMA_SHARE_ID`。

---

## 反爬策略（重要经验）

### TLS 指纹是最关键的检测维度

Python `requests` 和 `curl` 的 TLS 指纹（JA3）与真实浏览器完全不同，微信等平台可以一眼识别。

**实测数据（微信公众号文章）：**

| 方式 | TLS 指纹 | 反爬触发率 |
|------|----------|-----------|
| `requests.get()` / `curl` | Python/curl 指纹 | **40%**（10 篇触发 4 次"环境异常"） |
| Chrome CDP `cdp_fetch.js` | 真实 Chrome 指纹 | **0%**（1100 篇零触发） |

### 决策规则

| 场景 | 推荐方式 | 原因 |
|------|---------|------|
| 无反爬的公开页面 | `curl` / `requests` | 快速简单 |
| 有反爬的网站（微信、知乎等） | `cdp_fetch.js` | 真实浏览器指纹 |
| 需要登录态的页面 | `cdp_fetch.js` | 复用 Chrome Cookie |
| 图片/文件 CDN 下载 | `requests` + Referer 头 | CDN 不检查 TLS 指纹 |
| 批量爬取（>10 篇） | `batch_crawl.py` | 内置断点续传 + 反爬策略 |

### CDP fetch 用法

```bash
# 单页获取 HTML（输出文件大小到 stdout）
node scripts/cdp_fetch.js $CDP_PORT "https://example.com" /tmp/output.html

# 返回值：HTML 字节数（如 "3850007"）
# 错误时 exit code != 0，错误信息输出到 stderr
```

`cdp_fetch.js` 自动管理 Chrome 标签页（复用已有的 about:blank 或 mp.weixin 标签，避免标签泄漏）。

---

## 微信公众号文章

### 识别规则

以下 URL 模式应使用本节流程：
- `mp.weixin.qq.com/s/...` — 微信公众号文章
- `ima.qq.com/wiki/...` — IMA 知识库页面

### 抓取单篇公众号文章

```bash
OUTDIR="./output"
mkdir -p "$OUTDIR"

# 1. 用 CDP fetch 下载原始 HTML（真实浏览器指纹，避免反爬）
node scripts/cdp_fetch.js $CDP_PORT \
  "https://mp.weixin.qq.com/s/xxxxx" "$OUTDIR/raw.html"

# 2. 用脚本提取：生成 article.html + article.md + 本地图片
python3 scripts/wechat_extract.py "$OUTDIR/raw.html" "$OUTDIR/"
```

脚本会自动处理：
- BeautifulSoup 解析 `#js_content` 正文区域
- 下载所有图片到本地 `assets/` 目录（带 `Referer: https://mp.weixin.qq.com/` 头）
- HTML 和 Markdown 中的图片链接替换为本地路径
- 修复微信懒加载图片（`data-src` → `src`）
- 清除 `visibility:hidden` / `opacity:0` 隐藏元素
- 视频/音频替换为 `[视频: xxx]` / `[音频: xxx]` 占位符
- 提取文章标题、作者、发布日期

### wechat_extract.py 编程接口

批量场景可直接 import 使用，避免每篇都启动新进程：

```python
from wechat_extract import extract_article

result = extract_article(
    raw_html,           # 完整 HTML 字符串
    output_dir,         # 输出目录
    seq=1,              # 序号前缀（0 = 不加前缀）
    download_img=True,  # 是否下载图片
    session=session,    # 可选，复用 requests.Session
)
# result: {title, author, publish_time, source_url, dir_name,
#          html_path, md_path, img_stats, errors}
```

### 批量爬取（batch_crawl.py）

```bash
# 从 URL 列表爬取
python3 scripts/batch_crawl.py crawl urls.txt -o ./output/

# 单条 URL
python3 scripts/batch_crawl.py crawl "https://mp.weixin.qq.com/s/xxx" -o ./output/

# 断点续传（中断后重新运行，自动跳过已完成的文章）
python3 scripts/batch_crawl.py crawl -o ./output/

# 查看统计
python3 scripts/batch_crawl.py stats -o ./output/

# 重试失败
python3 scripts/batch_crawl.py retry -o ./output/

# 选项
#   --limit 10       只处理前 10 篇
#   --delay 3-8      请求间隔（秒）
#   --no-images      不下载图片
#   --force          重新处理已完成的
#   --cdp-port 9222  指定 CDP 端口
```

> **不要用 `curl` 或 `requests` 下载微信文章**——TLS 指纹会触发"环境异常"反爬页面。

### IMA 知识库批量爬取（ima_crawl.py）

IMA 知识库（ima.qq.com）是 SPA 应用。使用专用爬虫脚本 `ima_crawl.py` 进行批量爬取。
爬虫内部使用 `cdp_fetch.js` 通过 Chrome 获取页面（需要 debug Chrome 运行中）。

**输出目录结构：**
```
output/
├── manifest.json              # 全部文章元数据 + 爬取状态
└── articles/
    ├── 0001_文章标题/
    │   ├── raw.html           # 原始 HTML
    │   ├── article.html       # 干净 HTML（图片指向本地）
    │   ├── article.md         # Markdown（AI 可读）
    │   └── assets/            # 本地图片
    ├── 0002_文章标题/
    ...
```

**第一步：获取文章列表（需要 CDP 拦截认证头）**

```bash
# 1. 打开知识库分享页
agent-browser --cdp $CDP_PORT open "https://ima.qq.com/wiki/?shareId=<SHARE_ID>"

# 2. 用 CDP Fetch 域拦截 API 请求头（见下方"CDP 拦截 SPA API"章节）
#    保存到 /tmp/ima_headers.json

# 3. 用 headers 获取全部文章列表
python3 scripts/ima_crawl.py --phase=list --headers=/tmp/ima_headers.json -o ./ima_output/
# → 生成 manifest.json
```

**第二步：测试爬取（先试 10 篇确认质量）**

```bash
python3 scripts/ima_crawl.py --phase=crawl -o ./ima_output/ --limit=10
```

**第三步：全量爬取**

```bash
# 断点续传：中断后重新运行自动跳过已完成的文章
python3 scripts/ima_crawl.py --phase=crawl -o ./ima_output/
```

**其他命令：**

```bash
python3 scripts/ima_crawl.py --phase=stats -o ./ima_output/    # 查看爬取统计
python3 scripts/ima_crawl.py --phase=retry -o ./ima_output/    # 重试失败的文章
python3 scripts/ima_crawl.py --phase=crawl -o ./ima_output/ --force  # 强制重新爬取
```

**反爬策略（已内置）：**
- 通过 Chrome CDP 获取页面（真实 TLS 指纹，零反爬触发）
- 请求间隔 2-5 秒随机
- 失败指数退避重试（5s → 10s → 20s，最多 3 次）
- 反爬页面自动暂停 60 秒
- 每 200 篇暂停 20 秒
- 每篇完成后立即写入 manifest（断点续传）
- 图片下载用 requests（CDN 不查 TLS，带 Referer 头即可）

**实测结果：1100 篇，1087 成功（13 篇失败全是非网页附件），0 次反爬触发，144 分钟，4.75 GB。**

---

## CDP 拦截 SPA API（通用模式）

SPA 网站（如 ima.qq.com）的数据通过 JS 发起 API 请求获取，不在初始 HTML 中。用 CDP Fetch 域可以拦截这些请求，获取认证头和响应数据。

**步骤 1：写拦截脚本到文件**（避免 shell 转义问题）

```javascript
// /tmp/cdp_intercept.js
const TAB_ID = process.argv[2];
const CDP_PORT = process.argv[3] || "9222";
const API_PATTERN = process.argv[4] || "cgi-bin";  // 要拦截的 URL 关键词

const ws = new WebSocket(`ws://127.0.0.1:${CDP_PORT}/devtools/page/${TAB_ID}`);
let mid = 0;
const send = (method, params = {}) => {
  ws.send(JSON.stringify({ id: ++mid, method, params }));
  return mid;
};

ws.addEventListener("open", () => {
  send("Fetch.enable", { patterns: [{ urlPattern: `*${API_PATTERN}*`, requestStage: "Request" }] });
  setTimeout(() => send("Page.reload"), 1500);
});

ws.addEventListener("message", (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.method === "Fetch.requestPaused") {
    const req = msg.params.request;
    // 输出拦截到的请求信息
    process.stdout.write(JSON.stringify({
      url: req.url,
      method: req.method,
      headers: req.headers,
      postData: req.postData || null,
    }, null, 2) + "\n");
    // 放行请求（不阻断）
    send("Fetch.continueRequest", { requestId: msg.params.requestId });
  }
});

setTimeout(() => { ws.close(); process.exit(0); }, 20000);
```

**步骤 2：执行拦截**

```bash
# 找到目标标签页 ID
curl -s "http://127.0.0.1:$CDP_PORT/json" | python3 -c "
import sys, json
for t in json.load(sys.stdin):
    print(f'{t[\"id\"]}  {t[\"url\"][:80]}')
"

# 运行拦截，捕获 API 请求头
node /tmp/cdp_intercept.js <TAB_ID> $CDP_PORT "目标API关键词" > /tmp/intercepted.json
```

**注意事项：**
- 使用 `Fetch.enable` + `Fetch.requestPaused`（不是 `Network.requestWillBeSent`，后者拿不到完整 Cookie）
- 拦截后必须调用 `Fetch.continueRequest` 放行，否则请求会被挂起
- 拦截脚本**必须写到文件再用 `node` 执行**，不要用 `node -e "..."` 内联（shell 转义会出问题）
- 每个标签页同时只能有一个 WebSocket 调试连接

---

## 标准工作流程（通用网页）

### 第一步：侦察（小输出，可进上下文）

```bash
PAGE_TITLE=$(agent-browser --cdp $CDP_PORT get title)

agent-browser --cdp $CDP_PORT eval 'JSON.stringify({
  sections: document.querySelectorAll("section, article").length,
  headings: document.querySelectorAll("h1,h2,h3").length,
  items: document.querySelectorAll("[class*=item],[class*=card],[class*=post],[class*=entry]").length,
  height: document.body.scrollHeight,
  viewport: window.innerHeight
})'
```

### 第二步：提取内容 → 保存双格式文件

```bash
TS=$(date +%Y%m%d_%H%M%S)
OUTDIR="./output/$TS"
mkdir -p "$OUTDIR"
```

**保存 HTML（人类可读原始内容）：**

```bash
agent-browser --cdp $CDP_PORT eval '
(() => {
  const el = document.querySelector("article, main, [role=\"main\"], .content") || document.body;
  const title = document.title;
  const url = location.href;
  return "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>" + title +
    "</title><meta name=\"source-url\" content=\"" + url +
    "\"><style>body{max-width:800px;margin:40px auto;padding:0 20px;font-family:system-ui;line-height:1.6}img{max-width:100%}</style></head><body>" +
    "<p><small>Source: <a href=\"" + url + "\">" + url + "</a> | Saved: " + new Date().toISOString() + "</small></p><hr>" +
    el.innerHTML + "</body></html>";
})()
' > "$OUTDIR/page.html"
echo "HTML saved: $OUTDIR/page.html ($(wc -c < "$OUTDIR/page.html") bytes)"
```

**保存 Markdown（AI 可读结构化内容）：**

```bash
agent-browser --cdp $CDP_PORT eval "$(cat scripts/html2md.js)" > "$OUTDIR/page.md"
echo "Markdown saved: $OUTDIR/page.md ($(wc -c < "$OUTDIR/page.md") bytes)"
```

### 第三步：上传飞书文档

使用 `feishu_upload.py` 脚本（通过飞书 Open API 直接上传，支持图片）：

```bash
# 上传单篇（读取 markdown + assets/ 图片）
python3 scripts/feishu_upload.py article.md assets/
```

或在 Python 中调用：

```python
from feishu_upload import get_token, upload_article
from pathlib import Path

token = get_token()
result = upload_article(
    token,
    title="文章标题",
    md_path=Path("article.md"),
    assets_dir=Path("assets"),
)
# result: {doc_id, url, blocks_ok, blocks_total, imgs_ok, imgs_total}
print(result["url"])  # https://feishu.cn/docx/xxxxx
```

**飞书文档图片上传三步流程（关键！）：**

```
1. POST /docx/v1/documents/{doc_id}/blocks/{doc_id}/children
   body: {"children": [{"block_type": 27, "image": {}}], "index": -1}
   → 得到空图片 block 的 block_id

2. POST /drive/v1/medias/upload_all (multipart/form-data)
   data: file_name, parent_type="docx_image", parent_node=<block_id>, size
   files: file=<图片二进制>
   → 得到 file_token

3. PATCH /docx/v1/documents/{doc_id}/blocks/{block_id}
   body: {"replace_image": {"token": "<file_token>"}}
   → 图片关联完成，飞书中可正常显示
```

**注意：** 用 `replace_image` 而不是 `update_image`（后者会返回 invalid param）。

### 第四步：回复用户

回复消息中**只包含飞书文档链接**，不要贴任何原始内容。格式示例：

```
已提取 [页面标题] 的内容：
飞书文档：https://feishu.cn/docx/xxxxx
本地备份：./output/20260214_153000/
```

---

## 长页面 / 无限滚动的分块处理

当页面内容很多时，分块提取并**逐块追加到文件**：

```bash
OUTDIR="./output/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTDIR"

# 分块提取 Markdown，每块追加写入
agent-browser --cdp $CDP_PORT eval '
(() => {
  const items = document.querySelectorAll("article, [class*=post], [class*=entry], [class*=item]");
  return Array.from(items).slice(0, 10).map((el, i) =>
    "## Item " + (i+1) + "\n" + el.innerText.trim().slice(0, 2000)
  ).join("\n\n---\n\n");
})()
' > "$OUTDIR/page.md"
```

### 无限滚动页面（如知乎）

`agent-browser eval` 异步脚本超过 ~30 秒会超时。使用 **CDP WebSocket 直连**（Node.js `.mjs` 文件 + 原生 WebSocket）处理长时间滚动操作：

```javascript
// /tmp/scroll_load.mjs — Node 22+ 内置 WebSocket，无需 ws 模块
const TAB_ID = process.argv[2];
const CDP_PORT = process.argv[3] || '9223';
const ws = new WebSocket(`ws://127.0.0.1:${CDP_PORT}/devtools/page/${TAB_ID}`);
// ... 用 Runtime.evaluate 执行滚动 + 计数，无超时限制
```

**实测：知乎 213 个回答，一轮滚动即全部加载（5 次 scrollBy × 多轮，每轮 600ms 间隔）。**

### 飞书文档 API 要点

- **认证**：`POST /auth/v3/tenant_access_token/internal`，凭证从 `~/.chrome-crawl/config.json` 读取
- **创建文档**：`POST /docx/v1/documents`，body: `{"title": "...", "folder_token": ""}`
- **写入 blocks**：`POST /docx/v1/documents/{doc_id}/blocks/{doc_id}/children`（注意是 POST 不是 PATCH）
- **批量写入**：每批最多 30 个 blocks，遇到验证错误时降级为逐个写入
- **Rate Limit**：HTTP 429 时等待 2-6 秒重试
- **删除文档**：`DELETE /drive/v1/files/{doc_id}?type=docx`
- **Block 类型**：2=文本, 3=H1, 4=H2, 5=H3, 14=代码, 16=无序列表, 17=有序列表, 22=分割线, 27=图片
- **代码语言**：python=49, javascript=36, typescript=73, bash=7, json=38, html=32

---

## 提取特定信息（小输出可直接进上下文）

```bash
agent-browser --cdp $CDP_PORT eval 'JSON.stringify([...document.querySelectorAll("a")].map(a => ({t: a.innerText.trim().slice(0,80), h: a.href})).filter(a => a.t).slice(0, 50))'
```

## 交互（点击、填表等）

```bash
agent-browser --cdp $CDP_PORT snapshot -i
agent-browser --cdp $CDP_PORT click @e1
agent-browser --cdp $CDP_PORT fill @e2 "text"
```

---

## 规则

1. **内容写文件** — 超过 500 字的提取内容必须写入文件，不要让 eval 大输出直接进入上下文
2. **双格式保存** — 每次提取都保存 `.html`（人类可读）和 `.md`（AI 可读）
3. **上传飞书** — 提取完成后创建飞书文档写入 Markdown，回复用户只给飞书链接
4. **反爬网站用 CDP fetch** — 微信、知乎等有反爬的网站，必须用 `cdp_fetch.js` 通过 Chrome 获取页面，**不要用 curl/requests**（TLS 指纹会被检测）
5. **公众号文章用专用脚本** — `mp.weixin.qq.com` 文章用 `wechat_extract.py` 提取（自动下载图片到本地）
6. **批量爬取用 batch_crawl.py** — 超过 10 篇时用 `batch_crawl.py`，内置断点续传 + 反爬策略
7. **IMA 知识库用 ima_crawl.py** — `ima.qq.com` 用 `ima_crawl.py`，内置 CDP fetch + 断点续传
8. **SPA API 用 CDP Fetch 域拦截** — 需要拿 SPA 的 API 认证头时，用 `Fetch.enable` + `Fetch.requestPaused`，不要用 `Network.requestWillBeSent`
9. **CDP 脚本写文件执行** — Node.js CDP 脚本必须写到 `.js`/`.mjs` 文件再用 `node` 执行，不要用 `node -e "..."` 内联
10. **长时间操作用 CDP WebSocket 直连** — `agent-browser eval` 异步脚本超过 ~30 秒会超时。无限滚动等长操作用 Node.js `.mjs` 文件 + 原生 `WebSocket` 直连 CDP（Node 22+ 内置，无需 `ws` 模块）
11. **分块提取** — 每块不超过 2000 字/条目，每次最多 10 个条目
12. **滚动有上限** — 最多滚动 15 次，到底就停（无限滚动页面用 CDP 直连脚本，可突破此限制）
13. **Python 后台任务用 PYTHONUNBUFFERED=1** — 否则 print 输出被缓冲，看不到进度
14. **用 eval 不用 snapshot** — 提取文本内容用 `eval` 执行 JS
15. **侦察先行** — 先 `snapshot -i` 或 JS 统计，再决定提取策略
16. **不要登录** — Cookie 已同步
17. **Cookie 过期** — 告诉用户去普通 Chrome 重新登录，然后重新运行 `chrome_debug.sh`
18. **所有 agent-browser 命令** — 必须带 `--cdp $CDP_PORT`
19. **知乎图片 CDN 无需认证** — `zhimg.com` 图片用 `requests.get()` 直接下载，不需要 Referer 头（与微信 mmbiz 不同）
20. **私密信息不入代码** — Feishu 凭证、IMA share_id 等通过 `~/.chrome-crawl/config.json` 或环境变量配置

## 脚本参考

| 脚本 | 用途 |
|------|------|
| `chrome_debug.sh` | 启动调试 Chrome（同步 Cookie + 代理检测，支持 macOS/Linux） |
| `cdp_fetch.js` | **通过 Chrome CDP 获取页面 HTML（真实 TLS 指纹，防反爬）** |
| `html2md.js` | 浏览器内 HTML→Markdown 转换（通过 eval 注入） |
| `wechat_extract.py` | 微信公众号文章提取（BeautifulSoup + 图片下载 + HTML/MD 双格式） |
| `batch_crawl.py` | 批量爬虫（CDP fetch + URL 列表/单条 URL + 断点续传 + 反爬策略） |
| `ima_crawl.py` | IMA 知识库批量爬虫（CDP fetch + API 列表获取 + 断点续传） |
| `feishu_upload.py` | 飞书文档上传（Open API + 图片 3 步上传：空 block → 上传媒体 → replace_image） |
