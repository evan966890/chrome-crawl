# pinchtab 快速入门 — pinchtab Quickstart

pinchtab 是一个 12MB 的 Go 二进制程序，通过 **REST API** 控制 Chrome 浏览器。
它返回无障碍树（a11y tree）作为扁平 JSON，带稳定 ref 系统，内置人类级鼠标模拟和指纹轮换，面向多 Agent 系统和生产部署场景。

GitHub: https://github.com/pinchtab/pinchtab

---

## 安装

### 方式 1：直接下载二进制（推荐）

```bash
# Linux x86_64
curl -L https://github.com/pinchtab/pinchtab/releases/latest/download/pinchtab_linux_amd64.tar.gz | tar xz
sudo mv pinchtab /usr/local/bin/

# macOS Apple Silicon
curl -L https://github.com/pinchtab/pinchtab/releases/latest/download/pinchtab_darwin_arm64.tar.gz | tar xz
sudo mv pinchtab /usr/local/bin/

# macOS x86_64
curl -L https://github.com/pinchtab/pinchtab/releases/latest/download/pinchtab_darwin_amd64.tar.gz | tar xz
sudo mv pinchtab /usr/local/bin/

# 验证安装
pinchtab --version
```

### 方式 2：Docker

```bash
# 拉取并运行
docker run -d \
  --name pinchtab \
  -p 9867:9867 \
  pinchtab/pinchtab:latest

# 验证
curl http://localhost:9867/health
```

### 方式 3：自动启动（systemd）

```bash
# 创建 systemd 服务
sudo tee /etc/systemd/system/pinchtab.service > /dev/null <<EOF
[Unit]
Description=pinchtab browser bridge
After=network.target

[Service]
ExecStart=/usr/local/bin/pinchtab
Restart=always
RestartSec=3
Environment=BRIDGE_PORT=9867
Environment=BRIDGE_HEADLESS=false

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable pinchtab
sudo systemctl start pinchtab

# 查看状态
sudo systemctl status pinchtab
```

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BRIDGE_PORT` | `9867` | REST API 监听端口 |
| `BRIDGE_TOKEN` | `""` | Bearer Token 鉴权（生产环境必须设置） |
| `BRIDGE_HEADLESS` | `false` | 是否无头模式运行 Chrome |
| `BRIDGE_STEALTH` | `true` | 是否启用伪装模式（贝塞尔鼠标 + UA 随机化） |
| `BRIDGE_CHROME_PATH` | 自动检测 | 指定 Chrome 可执行文件路径 |
| `BRIDGE_USER_DATA_DIR` | 临时目录 | Chrome Profile 目录（设置后可持久化 Cookie） |
| `BRIDGE_MAX_TABS` | `20` | 最大同时打开标签页数 |
| `BRIDGE_TIMEOUT` | `30` | 单次操作超时时间（秒） |

```bash
# 示例：带鉴权 + 使用用户 Profile 启动
BRIDGE_TOKEN=mysecrettoken \
BRIDGE_USER_DATA_DIR=$HOME/.config/google-chrome \
BRIDGE_HEADLESS=false \
pinchtab
```

---

## 快速验证

```bash
# 1. 启动 pinchtab（前台运行，方便看日志）
pinchtab &

# 2. 健康检查
curl http://localhost:9867/health
# → {"status":"ok","version":"x.y.z"}

# 3. 打开页面
curl -X POST http://localhost:9867/navigate \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# 4. 获取交互元素快照（过滤模式，约 3.6k tokens）
curl "http://localhost:9867/snapshot?filter=interactive"

# 5. 点击元素
curl -X POST http://localhost:9867/actions \
  -H "Content-Type: application/json" \
  -d '[{"type": "click", "ref": "a11y-42"}]'
```

---

## 核心 API 端点

### GET /snapshot — 获取页面快照

返回 a11y tree 扁平 JSON，每个元素有稳定 `ref` 字段。

```bash
# 全量（约 29k tokens，慎用）
curl http://localhost:9867/snapshot

# 只返回可交互元素（约 3.6k tokens，推荐）
curl "http://localhost:9867/snapshot?filter=interactive"

# 响应示例
{
  "url": "https://example.com",
  "title": "Example Domain",
  "elements": [
    {"ref": "a11y-1", "role": "link", "name": "More information", "bounds": {...}},
    {"ref": "a11y-2", "role": "button", "name": "Submit", "bounds": {...}}
  ]
}
```

### POST /actions — 批量操作（单次请求）

将多个操作合并为单次 HTTP 请求，减少往返延迟。

```bash
curl -X POST http://localhost:9867/actions \
  -H "Content-Type: application/json" \
  -d '[
    {"type": "click",  "ref": "a11y-10"},
    {"type": "fill",   "ref": "a11y-11", "value": "hello@example.com"},
    {"type": "fill",   "ref": "a11y-12", "value": "mypassword"},
    {"type": "click",  "ref": "a11y-13"}
  ]'
```

支持的 action 类型：

| type | 必填字段 | 说明 |
|------|---------|------|
| `click` | `ref` | 点击元素 |
| `fill` | `ref`, `value` | 清空并填入文本 |
| `type` | `ref`, `value` | 追加输入文本（不清空） |
| `hover` | `ref` | 鼠标悬停 |
| `scroll` | `ref`, `direction` | 滚动（`up`/`down`/`left`/`right`） |
| `keypress` | `key` | 键盘按键（如 `Enter`, `Tab`, `Escape`） |
| `wait` | `ms` | 等待指定毫秒数 |
| `navigate` | `url` | 导航到 URL |
| `screenshot` | - | 截图（返回 base64） |

### POST /navigate — 导航

```bash
curl -X POST http://localhost:9867/navigate \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com", "waitUntil": "networkidle"}'

# waitUntil 选项：load | domcontentloaded | networkidle（默认 networkidle）
```

### POST /screenshot — 截图

```bash
curl -X POST http://localhost:9867/screenshot \
  -H "Content-Type: application/json" \
  -d '{"format": "png"}' \
  --output screenshot.png
```

### POST /fingerprint/rotate — 轮换指纹

```bash
# 轮换 UA、平台、分辨率（用于反检测）
curl -X POST http://localhost:9867/fingerprint/rotate

# 响应
{
  "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
  "platform": "Win32",
  "resolution": {"width": 1920, "height": 1080}
}
```

### GET /tabs — 标签页列表

```bash
curl http://localhost:9867/tabs

# 响应
[
  {"id": "tab-1", "url": "https://github.com", "title": "GitHub"},
  {"id": "tab-2", "url": "https://example.com", "title": "Example"}
]
```

### POST /tabs — 新建 / 切换标签页

```bash
# 新建标签页
curl -X POST http://localhost:9867/tabs \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# 切换到指定标签页
curl -X POST http://localhost:9867/tabs/tab-2/activate
```

---

## 与 AI Agent 集成

### Python 示例

```python
import requests

BASE = "http://localhost:9867"

def snapshot(interactive_only=True):
    params = {"filter": "interactive"} if interactive_only else {}
    return requests.get(f"{BASE}/snapshot", params=params).json()

def actions(steps: list[dict]):
    return requests.post(f"{BASE}/actions", json=steps).json()

def navigate(url: str):
    return requests.post(f"{BASE}/navigate", json={"url": url}).json()

# 示例：登录表单
navigate("https://example.com/login")
snap = snapshot()

# 找到用户名和密码字段的 ref
# (实际使用时由 AI 解析 snap["elements"] 找到对应 ref)
actions([
    {"type": "fill",  "ref": "a11y-5",  "value": "user@example.com"},
    {"type": "fill",  "ref": "a11y-6",  "value": "mypassword"},
    {"type": "click", "ref": "a11y-7"},   # 点击登录按钮
])
```

### Claude Code（MCP）集成示意

```python
# 在 AI 工具调用中封装 pinchtab API
def browser_snapshot() -> dict:
    """获取当前页面可交互元素列表"""
    return requests.get("http://localhost:9867/snapshot?filter=interactive").json()

def browser_act(actions: list) -> dict:
    """执行一批浏览器操作"""
    return requests.post("http://localhost:9867/actions", json=actions).json()
```

---

## 伪装 / 反检测功能

pinchtab 内置多项反检测机制，无需额外配置即可生效（`BRIDGE_STEALTH=true`）：

### 人类级鼠标模拟（贝塞尔曲线）

所有鼠标移动使用贝塞尔曲线轨迹模拟人类手部抖动，绕过鼠标轨迹检测：

```
直线移动（机器人特征）：  A ──────────── B
贝塞尔曲线（人类特征）：  A ~~~╮~╰~~~~~ B
```

### 指纹轮换

通过 `POST /fingerprint/rotate` 轮换以下特征：
- User-Agent 字符串（随机真实 UA）
- 平台标识（Windows / macOS / Linux）
- 屏幕分辨率
- 时区（与 UA 匹配）

### 其他内置伪装

- 隐藏 `navigator.webdriver` 标志
- 随机化 Canvas / WebGL 指纹
- 真实的 Chrome 扩展信号

---

## 会话持久化

pinchtab 在进程退出时自动保存当前所有标签页状态，下次启动时恢复：

```bash
# 设置持久化 Profile 目录（同时继承 Chrome Cookie）
BRIDGE_USER_DATA_DIR=$HOME/.pinchtab-profile pinchtab

# 进程退出后标签页状态保存在 Profile 目录
# 下次启动自动恢复所有标签页
```

> **注意**：如果要复用用户已有的 Chrome 登录态，将 `BRIDGE_USER_DATA_DIR` 指向真实 Chrome 的 Profile 目录（如 `$HOME/.config/google-chrome/Default`），但需要先关闭正在运行的 Chrome（同一 Profile 不能被两个进程同时打开）。

---

## 多 Tab 隔离（多 Agent 场景）

不同 Agent 可以控制不同 Tab，互不干扰：

```python
import threading
import requests

BASE = "http://localhost:9867"

def agent_task(agent_id: int, url: str):
    # 每个 Agent 创建自己的 Tab
    resp = requests.post(f"{BASE}/tabs", json={"url": url}).json()
    tab_id = resp["id"]

    # 在指定 Tab 上执行操作（带 tabId 参数）
    snap = requests.get(f"{BASE}/snapshot?tabId={tab_id}&filter=interactive").json()
    print(f"Agent {agent_id}: found {len(snap['elements'])} elements on {url}")

# 并行启动多个 Agent
threads = [
    threading.Thread(target=agent_task, args=(i, f"https://example.com/page{i}"))
    for i in range(5)
]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

---

## 与 chrome-crawl 中 CDP 方案对比

| 维度 | cdp_fetch.js（本项目） | pinchtab |
|------|----------------------|---------|
| **接口形式** | CDP WebSocket（Node.js 脚本） | REST API（任意语言调用） |
| **反检测** | 依赖真实 Chrome（无额外伪装） | 内置贝塞尔鼠标 + 指纹轮换 |
| **多 Agent 支持** | 需要手动管理标签页 | 原生 Tab 隔离 |
| **会话持久化** | 无 | ✅ 进程重启保留 Tab |
| **适用场景** | 批量爬取（内容读取为主） | 生产自动化（交互操作为主） |

---

## 常见问题

**Q：Chrome 启动失败？**
```bash
# 检查 Chrome 路径
which google-chrome || which chromium-browser || which chrome
# 手动指定
BRIDGE_CHROME_PATH=/usr/bin/google-chrome pinchtab
```

**Q：端口被占用？**
```bash
BRIDGE_PORT=9868 pinchtab
curl http://localhost:9868/health
```

**Q：如何在无显示器服务器上运行？**
```bash
# 无头模式
BRIDGE_HEADLESS=true pinchtab
# 或 Docker（已内置 Xvfb）
docker run -p 9867:9867 pinchtab/pinchtab:latest
```

**Q：生产环境如何鉴权？**
```bash
# 启动时设置 Token
BRIDGE_TOKEN=your-secret-token pinchtab

# 调用时带 Authorization 头
curl http://localhost:9867/snapshot \
  -H "Authorization: Bearer your-secret-token"
```
