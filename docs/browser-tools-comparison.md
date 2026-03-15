# 浏览器自动化工具对比 — Browser Automation Tools Comparison

本项目（chrome-crawl）集成并对比了三款主流 AI 驱动浏览器自动化工具（**agent-browser**、**browser-use**、**pinchtab**）以及经典代码驱动方案 **Puppeteer**。
前三款工具各有侧重，选错工具会显著增加 token 消耗或导致任务失败。Puppeteer 是生态最完善的传统方案，适合已知固定流程的自动化，但需要自己写代码，不适合直接作为 AI Agent 工具。

## 工具概览

### agent-browser（已集成）

- **定位**：Vercel 官方出品，轻量 CLI 工具，通过 snapshot+ref 系统操作真实 Chrome
- **适合**：简单任务、低 token 消耗场景
- **弱点**：对复杂页面的语义理解较弱，复杂多步交互容易失误
- **安装**：`npm install -g agent-browser && agent-browser install`
- **核心机制**：snapshot 获取带 ref 编号的交互元素列表，`click @ref` / `fill @ref` 操作，无需 DOM 选择器

```bash
# 典型用法
agent-browser --cdp $CDP_PORT snapshot -i -c    # 获取交互元素列表
agent-browser --cdp $CDP_PORT click @e13        # 按 ref 点击
agent-browser --cdp $CDP_PORT fill @e2 "text"   # 填写表单
```

### browser-use

- **定位**：更强的页面语义理解，支持直接使用用户自己的 Chrome Profile（含登录态）
- **适合**：复杂多步交互、需要现有登录状态的任务
- **弱点**：简单任务 token 消耗高于 agent-browser
- **安装**：从 Skill Hub 安装 `https://www.skill-cn.com/skill/51` 或执行 `npx skills add browser-use`
- **核心优势**：直接使用用户的真实 Chrome（含所有 Cookie/登录态），无需重新登录
- **触发方式**：对话中输入"用我的浏览器打开..."即可触发
- **Profile 选择**：支持指定浏览器 profile，实现登录态持久化

### pinchtab

- **定位**：12MB Go 二进制，通过 REST API 控制 Chrome，面向多 Agent 系统和生产部署
- **适合**：反检测/伪装场景、多 Agent 协作、需要会话持久化的生产环境
- **弱点**：需要独立进程运行，轻量脚本任务略显重
- **安装**：
  ```bash
  curl -L https://github.com/pinchtab/pinchtab/releases/latest/download/pinchtab_linux_amd64.tar.gz | tar xz
  # 或 Docker
  docker run -p 9867:9867 pinchtab/pinchtab:latest
  ```
- **核心机制**：返回 a11y tree（无障碍树）为扁平 JSON，稳定 ref 系统；内置人类级鼠标（贝塞尔曲线）、指纹轮换
- **GitHub**：https://github.com/pinchtab/pinchtab

### Puppeteer

- **定位**：Google 官方 Node.js 库，通过 CDP 控制 Chrome/Chromium，**生态最完善的代码驱动方案**，npm 周下载量超 600 万
- **适合**：已知固定流程的自动化、网页截图/PDF、爬虫脚本、AI 生成代码后由 Node.js 执行
- **弱点**：需要自己写代码，**不直接作为 AI Agent 工具**；对比 agent-browser/browser-use/pinchtab，无法让 AI Agent 开箱即用地操控浏览器
- **安装**：
  ```bash
  npm install puppeteer                            # 自带 Chromium
  npm install puppeteer-extra puppeteer-extra-plugin-stealth  # 反检测增强
  ```
- **核心优势**：成熟稳定（2018 年发布），文档完善，社区最大；`puppeteer-extra-plugin-stealth` 可消除 headless 指纹；`userDataDir` 直接复用用户 Chrome Profile
- **GitHub**：https://github.com/puppeteer/puppeteer

> **注意**：Puppeteer 是**传统代码驱动**方案。若任务是已知固定流程，Puppeteer 比 AI Agent 方案更快、更便宜、更可靠。若任务需要 AI 理解页面、做决策，则用上方三款 AI 驱动工具。

---

## 决策矩阵

| 场景 | 推荐工具 | 理由 |
|------|---------|------|
| 简单网页信息提取 | **agent-browser** | 更快，token 消耗低 |
| 复杂多步交互 | **browser-use** | 页面语义理解更强 |
| 需要现有登录状态的任务 | **browser-use** | 直接使用用户的真实 Chrome |
| 反检测 / 伪装场景 | **pinchtab** | 内置指纹轮换，人类级鼠标 |
| 多 Agent 浏览器控制 | **pinchtab** | REST API，Tab 隔离 |
| 网页截图 / PDF 生成 | **Puppeteer** | 最成熟，功能最完整 |
| 已知固定流程的批量自动化 | **Puppeteer** | 代码驱动，无 LLM token 消耗，快且可靠 |
| AI 生成脚本后执行 | **Puppeteer** | 作为底层执行层，AI 生成代码 + Puppeteer 运行 |
| 飞书文档编辑（浏览器操作） | 不推荐任何工具 | 太贵，请直接用飞书 Open API |
| CAPTCHA | 四款均需人工介入 | 所有工具都需要人工辅助 |

---

## Token 消耗对比（实测数据）

| 工具 | 简单任务 Token 成本 | 复杂任务 Token 成本 | 说明 |
|------|-------------------|-------------------|----|
| agent-browser | $0.76 | $5.23–16（波动较大） | AI Agent 驱动，需 LLM 理解页面 |
| browser-use | $1.40 | $3.76–9 | AI Agent 驱动，语义理解更强 |
| pinchtab | 最低（a11y tree 过滤优化） | 低–中 | AI Agent 驱动，a11y tree 大幅压缩 token |
| Puppeteer | **$0**（自动化本身） | **$0**（自动化本身） | 代码驱动，无 LLM 调用；若与 AI 集成（如解析内容）则额外计费 |

> **pinchtab 说明**：通过 `GET /snapshot?filter=interactive` 只返回可交互元素，token 从约 29k 压缩到约 3.6k（约 8 倍节省）。
>
> **Puppeteer 说明**：自动化执行本身不产生 LLM token 消耗。若将 Puppeteer 封装为 AI Agent 工具（如让 LLM 决定下一步操作），则按实际 LLM 调用计费。固定流程脚本无额外 AI 费用。

---

## 功能对比表

| 功能 | agent-browser | browser-use | pinchtab | Puppeteer |
|------|:---:|:---:|:---:|:---:|
| **驱动方式** | AI Agent | AI Agent | AI Agent | 代码脚本 |
| **CLI 命令行操作** | ✅ | ❌ | ❌ REST API | ❌ |
| **REST API 接口** | ❌ | ❌ | ✅ | ❌（需自行封装） |
| **使用用户 Chrome Profile** | ✅（CDP 连接） | ✅（直接使用） | ✅（CDP 连接） | ✅（userDataDir） |
| **复杂页面语义理解** | ⚠️ 一般 | ✅ 强 | ✅（a11y tree） | ❌（需自己写选择器） |
| **内置反检测 / 伪装** | ❌ | ❌ | ✅（贝塞尔鼠标 + 指纹） | ⚠️（需 stealth 插件） |
| **指纹轮换** | ❌ | ❌ | ✅ | ⚠️（第三方插件） |
| **多 Tab 管理** | ⚠️ 基础 | ⚠️ 基础 | ✅ 会话隔离 | ✅（编程控制） |
| **会话持久化（进程重启保留 Tab）** | ❌ | ❌ | ✅ | ⚠️（Cookie/Profile 持久化） |
| **Docker 支持** | ❌ | ❌ | ✅ | ✅ |
| **LLM Token 消耗** | ✅ 低 | ⚠️ 中 | ✅ 最低 | ✅✅ 零（自动化本身） |
| **登录态复用** | ✅（Chrome Cookie） | ✅（Profile 直用） | ✅（CDP Cookie） | ✅（Cookie / userDataDir） |
| **截图 / PDF 生成** | ⚠️ 基础 | ⚠️ 基础 | ⚠️ 基础 | ✅ 最完整 |
| **生态成熟度** | 新兴 | 新兴 | 新兴 | ✅✅ 最成熟（2018 年） |
| **无需编写代码** | ✅ | ✅ | ✅ | ❌（必须写代码） |

---

## 选型建议

```
任务类型判断树：

流程是否固定（已知步骤，无需 AI 决策）？
├── 是 → Puppeteer（代码驱动，零 token 消耗，最快最可靠）
│         特别适合：截图/PDF、批量爬虫、定时任务
└── 否（需要 AI 理解页面、动态决策）
    └── 需要登录态？
        ├── 否 → 简单页面？
        │   ├── 是 → agent-browser（最省 token）
        │   └── 否 → browser-use（语义理解更强）
        └── 是 → 生产/多 Agent 场景？
            ├── 是 → pinchtab（REST API + 会话隔离 + 反检测）
            └── 否 → browser-use（直接用你的 Chrome Profile）
```

---

## 参考文档

- agent-browser 集成：见 `SKILL.md`（浏览器 UI 自动化章节）
- browser-use 详细指南：见 `docs/browser-use-guide.md`
- pinchtab 快速入门：见 `docs/pinchtab-quickstart.md`
- Puppeteer 完整指南：见 `docs/puppeteer-guide.md`
