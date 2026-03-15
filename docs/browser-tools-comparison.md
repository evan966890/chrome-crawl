# 浏览器自动化工具对比 — Browser Automation Tools Comparison

本项目（chrome-crawl）集成并对比了三款主流 AI 驱动浏览器自动化工具（**agent-browser**、**browser-use**、**pinchtab**）以及经典代码驱动方案 **Puppeteer**，以及新增的 AI 原生框架 **Stagehand** 和云端浏览器基础设施 **Browserbase/Steel**。
前三款工具各有侧重，选错工具会显著增加 token 消耗或导致任务失败。Puppeteer 是生态最完善的传统方案，适合已知固定流程的自动化，但需要自己写代码，不适合直接作为 AI Agent 工具。Stagehand 是 AI 原生框架首选，Browserbase/Steel 解决云端浏览器基础设施问题。

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

### Stagehand（AI 原生框架）

- **定位**：Browserbase 团队出品的 AI 原生浏览器自动化框架，TypeScript SDK，基于 Playwright 构建但**比 Playwright 快 44%**（v3 直接走 CDP）
- **适合**：AI 原生任务、复杂交互、结构化数据提取、快速原型开发
- **弱点**：有 LLM token 消耗；目前主要支持 Chrome；固定流程任务不如纯代码方案经济
- **安装**：`npm install @stagehand/sdk`
- **核心原语**：
  - `act()` — 自然语言执行动作（"click the login button"）
  - `extract()` — 配合 Zod schema 提取结构化数据
  - `observe()` — 观察页面元素，辅助动态决策
  - **Agent 模式** — 给定高层目标，自动规划多步操作
- **GitHub**：https://github.com/browserbase/stagehand
- **官网**：https://www.stagehand.dev/

```typescript
// 示例：自然语言驱动，无需选择器
const stagehand = new Stagehand({ env: "LOCAL", modelName: "claude-3-5-sonnet-latest" });
await stagehand.init();
await stagehand.page.act("click the login button");
const data = await stagehand.page.extract({
  instruction: "extract all product prices",
  schema: z.object({ prices: z.array(z.string()) }),
});
```

> 详细指南见 `docs/stagehand-guide.md`

### Browserbase / Steel（云端浏览器基础设施）

这两款不是"操控浏览器的工具"，而是**提供浏览器运行环境的基础设施**，解决服务器端运行浏览器的痛点（IP 封禁、指纹检测、进程管理、扩缩容）。通常与 Stagehand、Playwright、Puppeteer 配合使用。

#### Browserbase（云托管）
- **定位**：云端 headless 浏览器平台，专为 AI agent 设计
- **核心优势**：内置 Stealth Mode、代理轮换、Session 持久化、自动扩缩容、Live Debug
- **免费套餐**：100 sessions/月
- **官网**：https://www.browserbase.com/

```typescript
import { Browserbase } from "@browserbase/sdk";
import { chromium } from "playwright";
const bb = new Browserbase({ apiKey: "..." });
const session = await bb.sessions.create({ projectId: "..." });
const browser = await chromium.connectOverCDP(session.connectUrl);
```

#### Steel（自托管开源）
- **定位**：开源自托管云浏览器基础设施，类似 Browserbase 但数据不出内网
- **核心优势**：MIT 开源、Docker 一键部署、CDP 兼容、企业内网友好
- **GitHub**：https://github.com/steel-dev/steel-browser

```bash
docker run -d -p 3000:3000 ghcr.io/steel-dev/steel-browser:latest
```

> 详细指南见 `docs/browserbase-steel-guide.md`

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
| **AI 原生 + 复杂交互 + 快速开发** | **Stagehand** | 自然语言驱动，无需选择器，extract() 直出结构化数据 |
| **结构化数据提取（爬虫）** | **Stagehand** | extract() + Zod schema，类型安全，无需手写解析 |
| **大规模生产环境 AI Agent** | **Stagehand + Browserbase** | 云端扩缩容 + 反检测 + Session 管理，开箱即用 |
| **企业内网 / 数据不出境** | **任意工具 + Steel** | Steel 自托管，数据完全可控 |
| 飞书文档编辑（浏览器操作） | 不推荐任何工具 | 太贵，请直接用飞书 Open API |
| CAPTCHA | 六款均需人工介入 | 所有工具都需要人工辅助 |

---

## Token 消耗对比（实测数据）

| 工具 | 简单任务 Token 成本 | 复杂任务 Token 成本 | 说明 |
|------|-------------------|-------------------|----|
| agent-browser | $0.76 | $5.23–16（波动较大） | AI Agent 驱动，需 LLM 理解页面 |
| browser-use | $1.40 | $3.76–9 | AI Agent 驱动，语义理解更强 |
| pinchtab | 最低（a11y tree 过滤优化） | 低–中 | AI Agent 驱动，a11y tree 大幅压缩 token |
| Puppeteer | **$0**（自动化本身） | **$0**（自动化本身） | 代码驱动，无 LLM 调用；若与 AI 集成（如解析内容）则额外计费 |
| Stagehand | 低–中（act/extract 各一次调用） | 中（多步 act + extract） | 每个原语调用一次 LLM；Agent 模式消耗更高 |
| Browserbase/Steel | 取决于配合的工具 | 取决于配合的工具 | 基础设施层，本身不产生 LLM 消耗；仅收 Session 费用（Browserbase）或服务器成本（Steel） |

> **pinchtab 说明**：通过 `GET /snapshot?filter=interactive` 只返回可交互元素，token 从约 29k 压缩到约 3.6k（约 8 倍节省）。
>
> **Puppeteer 说明**：自动化执行本身不产生 LLM token 消耗。若将 Puppeteer 封装为 AI Agent 工具（如让 LLM 决定下一步操作），则按实际 LLM 调用计费。固定流程脚本无额外 AI 费用。
>
> **Stagehand 说明**：act/extract/observe 每次调用均触发一次 LLM 推理。Agent 模式涉及多轮规划，消耗更高。建议先用 observe() 探查，再决策是否 act()。

---

## 功能对比表

| 功能 | agent-browser | browser-use | pinchtab | Puppeteer | Stagehand | Browserbase/Steel |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| **驱动方式** | AI Agent | AI Agent | AI Agent | 代码脚本 | AI 原生（自然语言） | 基础设施（不直接驱动） |
| **CLI 命令行操作** | ✅ | ❌ | ❌ REST API | ❌ | ❌ | ❌ |
| **REST API 接口** | ❌ | ❌ | ✅ | ❌（需自行封装） | ❌ | ✅（Steel）/ ✅（BB SDK） |
| **使用用户 Chrome Profile** | ✅（CDP 连接） | ✅（直接使用） | ✅（CDP 连接） | ✅（userDataDir） | ✅（本地模式） | ⚠️（云端独立实例） |
| **复杂页面语义理解** | ⚠️ 一般 | ✅ 强 | ✅（a11y tree） | ❌（需自己写选择器） | ✅✅ 最强（AI 原生） | N/A |
| **内置反检测 / 伪装** | ❌ | ❌ | ✅（贝塞尔鼠标 + 指纹） | ⚠️（需 stealth 插件） | ❌（本地）/ ✅（BB云端） | ✅✅（Browserbase 专业级）/ ⚠️（Steel 基础） |
| **指纹轮换** | ❌ | ❌ | ✅ | ⚠️（第三方插件） | ❌（本地）/ ✅（BB云端） | ✅（Browserbase）/ ❌（Steel） |
| **多 Tab 管理** | ⚠️ 基础 | ⚠️ 基础 | ✅ 会话隔离 | ✅（编程控制） | ✅（继承 Playwright） | ✅ |
| **会话持久化（进程重启保留 Tab）** | ❌ | ❌ | ✅ | ⚠️（Cookie/Profile 持久化） | ✅（BB云端）/ ❌（本地） | ✅ |
| **Docker 支持** | ❌ | ❌ | ✅ | ✅ | ✅ | ✅✅ |
| **LLM Token 消耗** | ✅ 低 | ⚠️ 中 | ✅ 最低 | ✅✅ 零（自动化本身） | ⚠️ 中（每原语一次） | ✅✅ 零（基础设施层） |
| **登录态复用** | ✅（Chrome Cookie） | ✅（Profile 直用） | ✅（CDP Cookie） | ✅（Cookie / userDataDir） | ✅（BB Session 持久化） | ✅（Session 持久化） |
| **截图 / PDF 生成** | ⚠️ 基础 | ⚠️ 基础 | ⚠️ 基础 | ✅ 最完整 | ✅（继承 Playwright） | ✅（配合 Playwright） |
| **生态成熟度** | 新兴 | 新兴 | 新兴 | ✅✅ 最成熟（2018 年） | 新兴（2024） | 新兴（2024） |
| **无需编写代码** | ✅ | ✅ | ✅ | ❌（必须写代码） | ✅（自然语言） | ❌（需配合其他工具） |
| **结构化数据提取** | ⚠️ 手动解析 | ⚠️ 手动解析 | ⚠️ 手动解析 | ❌（需手写） | ✅✅ extract() + Zod | N/A |
| **云端扩缩容** | ❌ | ❌ | ❌（需自建） | ❌（需自建） | ✅（配合 Browserbase） | ✅✅（Browserbase 原生）/ ⚠️（Steel 手动） |
| **自托管 / 数据不出境** | ✅ | ✅ | ✅ | ✅ | ✅（本地模式） | ✅✅（Steel 专为此设计） |

---

## 选型建议

```
任务类型判断树：

是否需要云端基础设施（大规模 / 反反爬 / 数据不出境）？
├── 数据不出境 → Steel（自托管）+ 任意工具
├── 大规模生产 / 反反爬 → Browserbase + Stagehand（推荐组合）
└── 否（本地运行）→ 继续判断：

    AI 原生 + 复杂交互（无需写选择器）？
    ├── 是 → Stagehand（自然语言驱动，extract() 直出结构化数据）
    └── 否 → 流程是否固定（已知步骤，无需 AI 决策）？
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
- Stagehand 使用指南：见 `docs/stagehand-guide.md`
- Browserbase & Steel 指南：见 `docs/browserbase-steel-guide.md`
