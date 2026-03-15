# Browserbase & Steel 云浏览器基础设施指南

云浏览器基础设施解决的核心问题：**在服务器上运行浏览器很痛**。
IP 被封、指纹识别、进程管理、扩缩容……Browserbase（云托管）和 Steel（自托管）提供了现成的解决方案。

---

## Browserbase

- **云托管** headless 浏览器平台，专为 AI agent 设计
- 解决服务器端运行浏览器的痛点：反检测、代理轮换、Session 管理、自动扩缩容
- 官网: https://www.browserbase.com/
- 免费套餐可用（100 sessions/month）

### 核心特性

| 特性 | 说明 |
|------|------|
| **Stealth Mode** | 内置反检测，可绕过 Cloudflare、DataDome 等反爬系统 |
| **Session Management** | 浏览器 Session 持久化，跨请求保留 Cookie/状态 |
| **Proxy Rotation** | 内置代理轮换，规避 IP 封禁 |
| **Live Debug** | 实时查看浏览器操作（可视化调试） |
| **Auto Scaling** | 并发 Session 自动扩缩容，无需管理服务器 |
| **CDP 兼容** | 标准 Chrome DevTools Protocol，Playwright/Puppeteer 可直接连接 |
| **录制回放** | Session 录制，方便排查问题 |

### 安装

```bash
npm install @browserbase/sdk
# Playwright 连接需要
npm install playwright
```

### 基础使用

```typescript
import { Browserbase } from "@browserbase/sdk";
import { chromium } from "playwright";

const bb = new Browserbase({
  apiKey: process.env.BROWSERBASE_API_KEY!,
});

async function run() {
  // 创建新 Session
  const session = await bb.sessions.create({
    projectId: process.env.BROWSERBASE_PROJECT_ID!,
  });

  // 通过 Playwright 连接云端浏览器
  const browser = await chromium.connectOverCDP(session.connectUrl);
  const page = browser.contexts()[0].pages()[0];

  // 正常使用 Playwright API
  await page.goto("https://example.com");
  const title = await page.title();
  console.log("页面标题:", title);

  await browser.close();
}

run().catch(console.error);
```

### Session 持久化 — 复用登录态

```typescript
import { Browserbase } from "@browserbase/sdk";
import { chromium } from "playwright";

const bb = new Browserbase({ apiKey: process.env.BROWSERBASE_API_KEY! });

// 首次登录：创建持久 Session 并保存 ID
async function loginAndSaveSession() {
  const session = await bb.sessions.create({
    projectId: process.env.BROWSERBASE_PROJECT_ID!,
    // keepAlive: true 保持 Session 活跃（付费功能）
  });

  const browser = await chromium.connectOverCDP(session.connectUrl);
  const page = browser.contexts()[0].pages()[0];

  await page.goto("https://app.example.com/login");
  await page.fill("#email", "user@example.com");
  await page.fill("#password", "mypassword");
  await page.click("button[type=submit]");
  await page.waitForNavigation();

  console.log("Session ID:", session.id);  // 保存此 ID
  await browser.close();
}

// 后续使用：直接恢复 Session（已有登录态）
async function reuseSession(sessionId: string) {
  const session = await bb.sessions.retrieve(sessionId);
  const browser = await chromium.connectOverCDP(session.connectUrl);
  const page = browser.contexts()[0].pages()[0];

  // 已有登录态，直接访问需要登录的页面
  await page.goto("https://app.example.com/dashboard");
  // ...
}
```

### 与 Stagehand 配合（推荐）

Browserbase 是 Stagehand 的官方云端后端，两者一起使用体验最佳：

```typescript
import { Stagehand } from "@stagehand/sdk";

const stagehand = new Stagehand({
  env: "BROWSERBASE",                            // 走云端
  apiKey: process.env.BROWSERBASE_API_KEY,
  projectId: process.env.BROWSERBASE_PROJECT_ID,
  modelName: "claude-3-5-sonnet-latest",
  modelClientOptions: {
    apiKey: process.env.ANTHROPIC_API_KEY,
  },
});

await stagehand.init();

// Stagehand 的 act/extract/observe 全部在 Browserbase 云端执行
await stagehand.page.act("search for 'AI tools' on the website");
const results = await stagehand.page.extract({
  instruction: "extract all search results",
  schema: z.object({ items: z.array(z.object({ title: z.string(), url: z.string() })) }),
});

await stagehand.close();
```

### 定价（2024 参考）

| 套餐 | Sessions/月 | 并发 | 价格 |
|------|------------|------|------|
| **Free** | 100 | 1 | $0 |
| **Developer** | 2,000 | 5 | $49/月 |
| **Team** | 10,000 | 20 | $299/月 |
| **Enterprise** | 自定义 | 自定义 | 联系销售 |

> 以官网最新定价为准：https://www.browserbase.com/pricing

### 适用场景

- **大规模 AI Agent 部署**：多 Agent 并行，无需管理浏览器进程
- **反反爬虫场景**：内置 Stealth Mode，绕过大多数检测
- **SaaS 产品集成**：给自家产品加浏览器能力，无需自维护基础设施
- **快速原型**：5 分钟接入，专注业务逻辑
- **成本可控**：按 Session 付费，小规模场景比自建服务器便宜

---

## Steel

- **自托管**的开源浏览器基础设施，类似 Browserbase 但可私有部署
- Docker 一键部署，数据不出内网
- GitHub: https://github.com/steel-dev/steel-browser
- 官网: https://steel.dev/

### 核心特性

| 特性 | 说明 |
|------|------|
| **完全自托管** | Docker 部署，数据留在自己服务器 |
| **CDP 兼容** | 标准 Chrome DevTools Protocol |
| **Session 管理** | 多 Session 并发管理 |
| **REST API** | HTTP API 控制浏览器 |
| **开源** | MIT 协议，可自由修改 |
| **基础反检测** | 相比 Browserbase 较基础 |

### 安装和部署

**Docker 一键部署（推荐）**：

```bash
# 拉取并运行 Steel
docker run -d \
  -p 3000:3000 \
  -p 9222:9222 \
  --name steel \
  ghcr.io/steel-dev/steel-browser:latest

# 验证运行状态
curl http://localhost:3000/health
```

**Docker Compose（生产推荐）**：

```yaml
# docker-compose.yml
version: "3.8"
services:
  steel:
    image: ghcr.io/steel-dev/steel-browser:latest
    ports:
      - "3000:3000"   # Steel API
      - "9222:9222"   # CDP 端口
    environment:
      - STEEL_API_KEY=your-secret-key   # 可选：API 鉴权
      - MAX_CONCURRENT_SESSIONS=10
    restart: unless-stopped
    volumes:
      - steel-data:/app/data

volumes:
  steel-data:
```

```bash
docker-compose up -d
```

### SDK 使用

```bash
npm install @steel-dev/steel
```

```typescript
import Steel from "@steel-dev/steel";
import { chromium } from "playwright";

const client = new Steel({
  baseUrl: "http://localhost:3000",  // 自托管地址
  // steelApiKey: "your-key",        // 若开启鉴权
});

async function run() {
  // 创建 Session
  const session = await client.sessions.create();
  console.log("Session ID:", session.id);

  // 通过 Playwright 连接
  const browser = await chromium.connectOverCDP(session.debuggerFullscreenUrl);
  const page = browser.contexts()[0].pages()[0];

  // 正常使用 Playwright
  await page.goto("https://example.com");
  const content = await page.content();
  console.log("页面内容长度:", content.length);

  // 关闭 Session
  await browser.close();
  await client.sessions.release(session.id);
}

run().catch(console.error);
```

### REST API 直接调用

```bash
# 创建 Session
curl -X POST http://localhost:3000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"timeout": 60000}'

# 响应：{ "id": "sess_abc123", "debuggerFullscreenUrl": "..." }

# 列出活跃 Sessions
curl http://localhost:3000/v1/sessions

# 释放 Session
curl -X DELETE http://localhost:3000/v1/sessions/sess_abc123
```

### 与 Stagehand 配合

Steel 也支持作为 Stagehand 的后端（本地/内网部署）：

```typescript
import { Stagehand } from "@stagehand/sdk";
import Steel from "@steel-dev/steel";
import { chromium } from "playwright";

const steelClient = new Steel({ baseUrl: "http://localhost:3000" });

// 手动创建 Session 并传给 Stagehand
const session = await steelClient.sessions.create();
const browser = await chromium.connectOverCDP(session.debuggerFullscreenUrl);

// 或直接用 Steel 的 Playwright 页面配合 Stagehand page
// （参考各自最新文档的集成方式）
```

---

## Browserbase vs Steel 对比

| 特性 | Browserbase | Steel |
|------|-------------|-------|
| **部署方式** | 云托管（SaaS） | 自托管（Docker） |
| **数据安全** | 数据在 Browserbase 服务器 | 数据留在自己服务器 |
| **扩缩容** | 自动（无需操心） | 手动（需运维） |
| **反检测能力** | 强（专业级 Stealth） | 基础 |
| **代理轮换** | 内置 | 需自行集成 |
| **Session 持久化** | ✅ 完善 | ✅ 基础支持 |
| **Live Debug** | ✅ 可视化实时查看 | ⚠️ 基础 |
| **成本模型** | 按 Session 付费 | 服务器自付（含运维） |
| **开源** | ❌ 闭源 | ✅ MIT 开源 |
| **上手难度** | 极低（注册即用） | 低（Docker 一键） |
| **Stagehand 集成** | 原生支持（官方推荐） | 需手动集成 |
| **适合场景** | SaaS 产品、个人开发者、快速原型 | 企业内网、政务、数据不出境要求 |

### 选型建议

```
数据能否出内网？
├── 不能 → Steel（自托管，数据完全可控）
└── 能 → 规模有多大？
    ├── 小（< 100 sessions/月）→ Browserbase Free（免费）
    ├── 中（100-10k sessions/月）→ Browserbase Developer/Team
    └── 大（> 10k sessions/月）→ 评估 Steel 自建 vs Browserbase Enterprise
```

---

## 实战：并行多 Agent 爬取

以下示例展示如何用 Browserbase 并行运行多个 AI Agent：

```typescript
import { Stagehand } from "@stagehand/sdk";
import { z } from "zod";

const URLS = [
  "https://news.example.com/tech",
  "https://news.example.com/business",
  "https://news.example.com/science",
];

async function scrapeWithAgent(url: string) {
  const stagehand = new Stagehand({
    env: "BROWSERBASE",
    apiKey: process.env.BROWSERBASE_API_KEY,
    projectId: process.env.BROWSERBASE_PROJECT_ID,
    modelName: "claude-3-5-sonnet-latest",
    modelClientOptions: { apiKey: process.env.ANTHROPIC_API_KEY },
  });

  await stagehand.init();
  await stagehand.page.goto(url);

  const data = await stagehand.page.extract({
    instruction: "extract the top 5 news article titles and summaries",
    schema: z.object({
      articles: z.array(
        z.object({
          title: z.string(),
          summary: z.string(),
          publishTime: z.string().optional(),
        })
      ),
    }),
  });

  await stagehand.close();
  return { url, articles: data.articles };
}

// 并行运行，Browserbase 自动管理多个浏览器实例
async function main() {
  const results = await Promise.all(URLS.map(scrapeWithAgent));
  results.forEach(({ url, articles }) => {
    console.log(`\n=== ${url} ===`);
    articles.forEach(a => console.log(`- ${a.title}`));
  });
}

main().catch(console.error);
```

---

## 参考资料

- Browserbase 官方文档: https://docs.browserbase.com/
- Browserbase GitHub: https://github.com/browserbase/browserbase
- Steel GitHub: https://github.com/steel-dev/steel-browser
- Steel 文档: https://docs.steel.dev/
- Stagehand（配合使用）: https://www.stagehand.dev/
