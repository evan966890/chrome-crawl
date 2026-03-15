# Stagehand 使用指南

## 概述

- **Browserbase 团队出品**的 AI 浏览器自动化框架
- TypeScript SDK，基于 Playwright 构建但比 Playwright **快 44%**（v3 重写后直接走 CDP）
- **3 个核心原语**：`act()`（执行动作）、`extract()`（提取数据）、`observe()`（观察页面）
- 另有 **Stagehand Agent 模式**用于高级自主决策
- GitHub: https://github.com/browserbase/stagehand
- 官网: https://www.stagehand.dev/

---

## 安装

```bash
npm install @stagehand/sdk
# 或使用脚手架快速创建项目
npx create-browser-app
```

初始化项目结构：

```
my-browser-app/
├── index.ts          # 主入口
├── package.json
└── tsconfig.json
```

---

## 三大核心原语

### act() — 执行动作

用自然语言描述动作，Stagehand 自动定位元素并执行，无需写选择器。

```typescript
import { Stagehand } from "@stagehand/sdk";
import { z } from "zod";

const stagehand = new Stagehand({
  env: "LOCAL",  // 或 "BROWSERBASE" 走云端
  modelName: "claude-3-5-sonnet-latest",  // 支持 Claude / GPT
  modelClientOptions: { apiKey: process.env.ANTHROPIC_API_KEY },
});

await stagehand.init();

// 导航
await stagehand.page.goto("https://example.com/login");

// 自然语言动作 — 自动找到登录按钮并点击
await stagehand.page.act("click the login button");

// 填写表单
await stagehand.page.act("fill in the email field with test@example.com");
await stagehand.page.act("fill in the password field with mypassword");
await stagehand.page.act("click the submit button");
```

**act() 适合场景**：
- 点击、填写、选择、滚动等标准交互
- 无需精确选择器，描述意图即可
- 处理动态渲染、样式变化的页面

---

### extract() — 提取结构化数据

配合 **Zod schema** 返回类型安全的结构化数据，无需手写解析逻辑。

```typescript
import { z } from "zod";

// 提取商品列表
const data = await stagehand.page.extract({
  instruction: "extract all product names and prices",
  schema: z.object({
    products: z.array(
      z.object({
        name: z.string(),
        price: z.string(),
        inStock: z.boolean().optional(),
      })
    ),
  }),
});

console.log(data.products);
// [{ name: "iPhone 15", price: "$999", inStock: true }, ...]

// 提取文章信息
const article = await stagehand.page.extract({
  instruction: "extract the article title, author, publication date, and main content",
  schema: z.object({
    title: z.string(),
    author: z.string(),
    publishDate: z.string(),
    content: z.string(),
    tags: z.array(z.string()).optional(),
  }),
});
```

**extract() 适合场景**：
- 爬取商品信息、文章内容、搜索结果
- 需要结构化 JSON 输出
- 页面结构不固定、难以写稳定的 CSS 选择器

---

### observe() — 观察页面

返回页面上匹配描述的元素列表，用于探查页面状态或动态决策。

```typescript
// 找到所有可点击的按钮
const buttons = await stagehand.page.observe("find all clickable buttons");
console.log(buttons);
// [{ selector: "button#submit", description: "Submit form" }, ...]

// 检查特定元素是否存在
const loginOptions = await stagehand.page.observe(
  "find all available login methods (Google, GitHub, email)"
);

// 根据观察结果动态决策
if (loginOptions.some(el => el.description.includes("Google"))) {
  await stagehand.page.act("click the Google login button");
} else {
  await stagehand.page.act("click the email login button");
}
```

**observe() 适合场景**：
- 在 act() 之前探查页面，避免盲目操作
- 多分支流程中动态选择路径
- 调试：了解 Stagehand 如何理解当前页面

---

## 完整示例：电商数据抓取

```typescript
import { Stagehand } from "@stagehand/sdk";
import { z } from "zod";

async function scrapeProducts() {
  const stagehand = new Stagehand({
    env: "LOCAL",
    modelName: "claude-3-5-sonnet-latest",
    modelClientOptions: { apiKey: process.env.ANTHROPIC_API_KEY },
    verbose: 1,  // 0=silent, 1=info, 2=debug
  });

  await stagehand.init();

  try {
    // 1. 导航到商品页
    await stagehand.page.goto("https://shop.example.com/products");

    // 2. 搜索特定商品
    await stagehand.page.act("search for 'wireless headphones'");

    // 3. 等待结果加载（act 会自动等待）
    await stagehand.page.act("wait for search results to load");

    // 4. 提取结构化数据
    const result = await stagehand.page.extract({
      instruction: "extract all product listings from the search results",
      schema: z.object({
        products: z.array(
          z.object({
            name: z.string(),
            price: z.string(),
            rating: z.number().optional(),
            reviewCount: z.number().optional(),
            url: z.string().optional(),
          })
        ),
        totalResults: z.number().optional(),
      }),
    });

    console.log(`找到 ${result.totalResults} 个商品`);
    return result.products;

  } finally {
    await stagehand.close();
  }
}

scrapeProducts().then(console.log).catch(console.error);
```

---

## Stagehand Agent 模式

Agent 模式用于高级自主决策，给定目标后自动规划并执行多步操作，适合复杂长链路任务。

```typescript
import { Stagehand, StagehandAgent } from "@stagehand/sdk";

const stagehand = new Stagehand({
  env: "LOCAL",
  modelName: "claude-3-5-sonnet-latest",
  modelClientOptions: { apiKey: process.env.ANTHROPIC_API_KEY },
});

await stagehand.init();

// 创建 Agent，指定高层目标
const agent = stagehand.agent({
  modelName: "claude-opus-4-5",  // Agent 模式推荐用更强的模型
  instructions: "你是一个电商数据分析助手，帮助用户查找最优惠的商品",
});

// 直接给目标，Agent 自动规划步骤
const result = await agent.execute(
  "在 amazon.com 搜索 'mechanical keyboard'，找到评分最高的三款，" +
  "比较价格和规格，返回推荐结果"
);

console.log(result);
await stagehand.close();
```

**Agent 模式适合场景**：
- 多步骤、需要中间决策的复杂任务
- 不确定页面结构、需要自适应的场景
- 类似"帮我完成...整个流程"的高层指令

---

## 与 Browserbase 云端配合

Stagehand 既可本地运行，也可通过 **Browserbase 云端**运行：

```typescript
// 云端模式：自动扩缩容 + 反检测 + Session 管理
const stagehand = new Stagehand({
  env: "BROWSERBASE",
  apiKey: process.env.BROWSERBASE_API_KEY,
  projectId: process.env.BROWSERBASE_PROJECT_ID,
  modelName: "claude-3-5-sonnet-latest",
  modelClientOptions: { apiKey: process.env.ANTHROPIC_API_KEY },
});

await stagehand.init();
// 后续用法与本地模式完全相同
await stagehand.page.act("click the login button");
```

云端运行优势：
- 无需本地 Chrome 环境
- 内置反检测（绕过 Cloudflare 等）
- 自动 Session 持久化
- 并行多实例扩缩容

---

## 与 Playwright 对比

| 特性 | Stagehand | Playwright |
|------|-----------|------------|
| **驱动方式** | AI 自然语言 | 代码 + 选择器 |
| **速度** | 比 Playwright 快 44%（v3 CDP 直连） | 基准 |
| **学习成本** | 极低（描述意图即可） | 中等（需学 API + 选择器） |
| **选择器** | 不需要 | CSS / XPath / Role |
| **结构化数据提取** | 内置 `extract()` + Zod | 需手写解析逻辑 |
| **页面变动适应性** | 强（AI 自适应） | 弱（选择器失效即报错） |
| **跨浏览器支持** | Chrome（通过 CDP） | Chrome / Firefox / WebKit |
| **LLM 模型支持** | Claude / GPT / Gemini | N/A |
| **云端扩缩容** | 原生支持（Browserbase） | 需自行搭建基础设施 |
| **调试能力** | observe() 辅助 + Browserbase Live Debug | Playwright Inspector |
| **成本** | 有 LLM token 消耗 | 零 LLM 消耗 |

> **何时选 Stagehand vs Playwright**：
> - 页面结构不固定 / 经常变动 → Stagehand（AI 自适应，无需维护选择器）
> - 大批量固定流程、对成本敏感 → Playwright / Puppeteer（零 token 消耗）
> - 快速原型 / 一次性任务 → Stagehand（开发效率极高）

---

## 适用场景总结

| 场景 | 推荐 | 原因 |
|------|------|------|
| 复杂网页表单填写 | ✅ Stagehand | 自然语言描述，无需找选择器 |
| 多步登录/认证流程 | ✅ Stagehand | act() 序列自动执行 |
| 结构化数据提取（爬虫） | ✅ Stagehand | extract() + Zod 直出类型安全数据 |
| UI 自动化测试（快速原型） | ✅ Stagehand | 无需维护选择器，省维护成本 |
| 生产环境大规模爬取 | ✅ Stagehand + Browserbase | 云端扩缩容 + 反检测 |
| 已知固定流程批量执行 | ❌ 用 Playwright/Puppeteer | token 消耗不合算 |

---

## 参考资料

- 官方文档: https://www.stagehand.dev/
- GitHub: https://github.com/browserbase/stagehand
- Browserbase 云端平台: https://www.browserbase.com/
- Zod schema 文档: https://zod.dev/
