# Puppeteer 使用指南

## 概述

- **维护方**：Google 官方维护的 Node.js 库，通过 Chrome DevTools Protocol (CDP) 控制 Chrome/Chromium
- **成熟度**：最成熟的浏览器自动化方案之一，生态最完善，npm 周下载量超 600 万
- **模式**：支持 headless 和 headed（有界面）模式
- **定位**：代码驱动，适合开发者自己写脚本，而非 AI Agent 直接调用
- **GitHub**：https://github.com/puppeteer/puppeteer
- **文档**：https://pptr.dev

---

## 安装

```bash
# 方式一：自带 Chromium（推荐新手，开箱即用）
npm install puppeteer

# 方式二：不带 Chromium，使用系统已安装的 Chrome（包体更小）
npm install puppeteer-core
```

> **注意**：`puppeteer` 安装时会自动下载兼容版本的 Chromium（约 300MB）。
> 如果只装 `puppeteer-core`，需要手动指定 Chrome 路径（见下方示例）。

---

## 核心用法

### 1. 启动浏览器与新建页面

```js
const puppeteer = require('puppeteer');

(async () => {
  // 使用内置 Chromium
  const browser = await puppeteer.launch({
    headless: 'new',   // 'new' = 新 headless 模式；false = 有界面
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 720 });

  await page.goto('https://example.com');
  console.log(await page.title());

  await browser.close();
})();
```

```js
// 使用系统 Chrome（puppeteer-core）
const puppeteer = require('puppeteer-core');

const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  // Windows: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
  headless: false,
});
```

---

### 2. 导航与等待

```js
// 等待页面加载完成
await page.goto('https://example.com', { waitUntil: 'networkidle2' });
// waitUntil 选项：
//   'load'           - 触发 load 事件
//   'domcontentloaded' - 触发 DOMContentLoaded
//   'networkidle0'   - 500ms 内无网络请求
//   'networkidle2'   - 500ms 内最多 2 个网络请求（推荐）

// 等待某个元素出现
await page.waitForSelector('#login-btn', { timeout: 5000 });

// 等待某个函数返回 true
await page.waitForFunction(() => document.querySelector('.loaded') !== null);

// 等待导航完成（点击链接后用）
await Promise.all([
  page.waitForNavigation({ waitUntil: 'networkidle2' }),
  page.click('a#submit'),
]);
```

---

### 3. 点击与填写表单

```js
// 点击按钮
await page.click('#submit-btn');

// 填写输入框（先清空再输入）
await page.click('#username');
await page.keyboard.down('Control');
await page.keyboard.press('A');
await page.keyboard.up('Control');
await page.type('#username', 'myuser', { delay: 50 }); // delay 模拟真人输入

// 选择下拉框
await page.select('#country', 'CN');

// 勾选 checkbox
await page.click('#agree-checkbox');

// 上传文件
const fileInput = await page.$('input[type="file"]');
await fileInput.uploadFile('/path/to/file.pdf');
```

---

### 4. 截图与 PDF

```js
// 截图（当前视口）
await page.screenshot({ path: 'screenshot.png' });

// 全页面截图
await page.screenshot({ path: 'full-page.png', fullPage: true });

// 截图返回 Buffer（不保存文件）
const buffer = await page.screenshot({ encoding: 'binary' });

// 生成 PDF（仅 headless 模式可用）
await page.pdf({
  path: 'output.pdf',
  format: 'A4',
  printBackground: true,
  margin: { top: '1cm', bottom: '1cm', left: '1cm', right: '1cm' },
});
```

---

### 5. Cookie 管理

```js
// 获取当前页面所有 Cookie
const cookies = await page.cookies();
console.log(cookies);

// 设置 Cookie
await page.setCookie({
  name: 'session_token',
  value: 'abc123xyz',
  domain: 'example.com',
  path: '/',
  httpOnly: true,
  secure: true,
});

// 批量导入 Cookie（从文件恢复登录态）
const fs = require('fs');
const savedCookies = JSON.parse(fs.readFileSync('cookies.json', 'utf8'));
await page.setCookie(...savedCookies);

// 导出 Cookie 到文件
const currentCookies = await page.cookies();
fs.writeFileSync('cookies.json', JSON.stringify(currentCookies, null, 2));

// 删除某个 Cookie
await page.deleteCookie({ name: 'session_token', domain: 'example.com' });
```

---

### 6. 拦截网络请求

```js
// 开启请求拦截
await page.setRequestInterception(true);

page.on('request', (req) => {
  // 拦截图片和字体，加快加载速度
  if (['image', 'font'].includes(req.resourceType())) {
    req.abort();
  } else {
    req.continue();
  }
});

// 监听响应（抓取 API 数据）
page.on('response', async (response) => {
  if (response.url().includes('/api/data')) {
    const data = await response.json();
    console.log('API Response:', data);
  }
});
```

---

### 7. 执行 JavaScript（page.evaluate）

```js
// 在页面上下文中执行 JS，获取返回值
const title = await page.evaluate(() => document.title);

// 传参数给页面 JS
const text = await page.evaluate((selector) => {
  return document.querySelector(selector)?.textContent?.trim();
}, '#main-content');

// 操作 DOM
await page.evaluate(() => {
  document.querySelector('.cookie-banner')?.remove();
  window.scrollTo(0, document.body.scrollHeight);
});

// 获取多个元素的属性
const links = await page.evaluate(() =>
  Array.from(document.querySelectorAll('a')).map((a) => ({
    text: a.textContent.trim(),
    href: a.href,
  }))
);
```

---

### 8. 文件下载处理

```js
const path = require('path');

// 设置下载目录
const client = await page.target().createCDPSession();
await client.send('Page.setDownloadBehavior', {
  behavior: 'allow',
  downloadPath: path.resolve('./downloads'),
});

// 触发下载（点击下载按钮）
await page.click('#download-btn');

// 等待文件出现（简单实现）
const fs = require('fs');
const downloadDir = './downloads';
await new Promise((resolve) => {
  const interval = setInterval(() => {
    const files = fs.readdirSync(downloadDir).filter((f) => !f.endsWith('.crdownload'));
    if (files.length > 0) {
      clearInterval(interval);
      resolve(files[0]);
    }
  }, 500);
});
```

---

## 反检测

默认 Puppeteer 有一些 headless 指纹特征（如 `navigator.webdriver = true`），容易被检测。使用 `puppeteer-extra` + stealth 插件可消除大部分特征。

### 安装

```bash
npm install puppeteer-extra puppeteer-extra-plugin-stealth
```

### 用法

```js
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');

// 启用 stealth 插件（一行搞定）
puppeteer.use(StealthPlugin());

(async () => {
  const browser = await puppeteer.launch({ headless: 'new' });
  const page = await browser.newPage();

  // 测试：访问检测页面，验证 webdriver 标志是否被清除
  await page.goto('https://bot.sannysoft.com');
  await page.screenshot({ path: 'stealth-test.png', fullPage: true });

  await browser.close();
})();
```

> stealth 插件会自动处理：`navigator.webdriver`、`navigator.plugins`、`navigator.languages`、Canvas 指纹、WebGL 指纹、Chrome 运行时对象等约 11 项检测点。

---

## 登录态持久化

### 方式一：复用用户 Chrome Profile（userDataDir）

```js
const puppeteer = require('puppeteer');

// 使用已有的 Chrome Profile，继承所有 Cookie 和登录态
const browser = await puppeteer.launch({
  headless: false, // 首次可能需要手动登录
  userDataDir: '/Users/yourname/Library/Application Support/Google/Chrome/Default',
  // Windows: 'C:\\Users\\YourName\\AppData\\Local\\Google\\Chrome\\User Data\\Default'
  executablePath: puppeteer.executablePath(), // 或系统 Chrome 路径
});

const page = await browser.newPage();
await page.goto('https://mail.google.com');
// 如果 Profile 已登录，这里无需再次登录
```

### 方式二：Cookie 导入导出

```js
// 登录一次后保存 Cookie
const cookieSaver = async () => {
  const browser = await puppeteer.launch({ headless: false });
  const page = await browser.newPage();
  await page.goto('https://example.com/login');

  // 手动登录或自动登录...
  await page.type('#username', 'user');
  await page.type('#password', 'pass');
  await page.click('#login');
  await page.waitForNavigation();

  // 保存 Cookie
  const cookies = await page.cookies();
  require('fs').writeFileSync('cookies.json', JSON.stringify(cookies));

  await browser.close();
};

// 之后每次复用 Cookie
const cookieUser = async () => {
  const browser = await puppeteer.launch({ headless: 'new' });
  const page = await browser.newPage();

  // 先导入 Cookie，再访问页面
  const cookies = JSON.parse(require('fs').readFileSync('cookies.json', 'utf8'));
  await page.setCookie(...cookies);

  await page.goto('https://example.com/dashboard'); // 直接进入已登录页面
  await browser.close();
};
```

### 方式三：localStorage / sessionStorage

```js
// 保存存储状态
const storageState = await page.evaluate(() => ({
  localStorage: Object.fromEntries(
    Object.keys(localStorage).map((k) => [k, localStorage.getItem(k)])
  ),
  sessionStorage: Object.fromEntries(
    Object.keys(sessionStorage).map((k) => [k, sessionStorage.getItem(k)])
  ),
}));
require('fs').writeFileSync('storage.json', JSON.stringify(storageState));

// 恢复存储状态
const state = JSON.parse(require('fs').readFileSync('storage.json', 'utf8'));
await page.evaluate((s) => {
  Object.entries(s.localStorage).forEach(([k, v]) => localStorage.setItem(k, v));
  Object.entries(s.sessionStorage).forEach(([k, v]) => sessionStorage.setItem(k, v));
}, state);
await page.reload();
```

---

## 适用场景

| 场景 | 适合度 | 说明 |
|------|--------|------|
| 网页截图 / PDF 生成 | ⭐⭐⭐⭐⭐ | 最佳方案，功能最完整 |
| 表单自动化 | ⭐⭐⭐⭐ | 成熟稳定，文档丰富 |
| 网页爬虫 | ⭐⭐⭐⭐ | 需配合 stealth 插件反检测 |
| SPA 数据提取 | ⭐⭐⭐⭐⭐ | 完整 JS 执行环境，可直接调 API |
| E2E 自动化测试 | ⭐⭐⭐ | 可用，但 Playwright 更适合测试场景 |
| AI Agent 调用 | ⭐⭐ | 需要额外封装，不如 agent-browser/browser-use 开箱即用 |
| 生产环境爬虫服务 | ⭐⭐⭐⭐⭐ | 成熟，有大量生产案例 |

---

## 与 Playwright 对比

| 特性 | Puppeteer | Playwright |
|------|-----------|------------|
| **维护方** | Google | Microsoft |
| **支持浏览器** | Chrome / Chromium | Chrome / Firefox / WebKit (Safari) |
| **语言支持** | Node.js（官方）；其他语言有第三方绑定 | Node.js / Python / Java / C# |
| **自动等待** | 需手动 `waitForSelector` 等 | 内置智能等待（auto-wait） |
| **移动端模拟** | 基础（device 描述符） | 完善（Emulation API） |
| **调试工具** | DevTools Protocol 直接调试 | Playwright Inspector / Codegen |
| **并发架构** | 单进程多 Page | BrowserContext 隔离（推荐） |
| **社区生态** | 最大（历史最久） | 快速增长，微软持续投入 |
| **反检测插件** | puppeteer-extra-plugin-stealth | 需手动配置（无官方 stealth） |
| **npm 周下载** | ~600 万 | ~300 万 |
| **适合场景** | 爬虫、截图、已有 Puppeteer 项目 | 测试、跨浏览器、新项目 |

---

## 在 chrome-crawl 中的定位

本项目主要面向 AI Agent 驱动的自动化场景（agent-browser / browser-use / pinchtab）。Puppeteer 是**代码驱动**方案，不直接作为 AI Agent 的工具，但可以：

1. **作为底层执行层**：AI Agent 生成 Puppeteer 脚本，由 Node.js 执行
2. **与 AI 集成**：结合 LangChain / AI SDK，用 AI 解析页面内容，用 Puppeteer 执行操作
3. **批量任务**：已知流程的重复性任务（登录→操作→退出），直接写 Puppeteer 脚本效率最高
4. **截图 / PDF 服务**：作为后端服务，按需渲染页面

> 如果你的任务是**已知固定流程**的自动化，Puppeteer 通常比 AI Agent 方案更快、更便宜、更可靠。
> 如果任务需要**理解页面、做决策**，则使用 agent-browser / browser-use / pinchtab + LLM 方案。

---

## 常用代码片段合集

### 带 stealth 的完整启动模板

```js
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const { executablePath } = require('puppeteer');

puppeteer.use(StealthPlugin());

async function createBrowser({ headless = 'new', userDataDir = null } = {}) {
  const opts = {
    headless,
    executablePath: executablePath(),
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-blink-features=AutomationControlled',
    ],
  };
  if (userDataDir) opts.userDataDir = userDataDir;
  return puppeteer.launch(opts);
}

module.exports = { createBrowser };
```

### 复用用户 Chrome

```js
// macOS Chrome Profile
const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  userDataDir: `${process.env.HOME}/Library/Application Support/Google/Chrome/Default`,
  headless: false,
});
```

### Cookie 导入导出工具函数

```js
const fs = require('fs');

async function saveCookies(page, filePath) {
  const cookies = await page.cookies();
  fs.writeFileSync(filePath, JSON.stringify(cookies, null, 2));
  console.log(`Saved ${cookies.length} cookies to ${filePath}`);
}

async function loadCookies(page, filePath) {
  if (!fs.existsSync(filePath)) return false;
  const cookies = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  await page.setCookie(...cookies);
  console.log(`Loaded ${cookies.length} cookies from ${filePath}`);
  return true;
}
```

### 网络请求拦截（屏蔽广告/图片加速）

```js
await page.setRequestInterception(true);
const BLOCKED_TYPES = new Set(['image', 'media', 'font', 'stylesheet']);
const BLOCKED_DOMAINS = ['doubleclick.net', 'googlesyndication.com', 'adservice.google.com'];

page.on('request', (req) => {
  const url = req.url();
  if (
    BLOCKED_TYPES.has(req.resourceType()) ||
    BLOCKED_DOMAINS.some((d) => url.includes(d))
  ) {
    req.abort();
  } else {
    req.continue();
  }
});
```

### 等待和超时处理（健壮版）

```js
async function safeClick(page, selector, timeout = 5000) {
  try {
    await page.waitForSelector(selector, { visible: true, timeout });
    await page.click(selector);
    return true;
  } catch (e) {
    console.warn(`safeClick: selector "${selector}" not found within ${timeout}ms`);
    return false;
  }
}

async function safeGetText(page, selector, defaultValue = '') {
  try {
    await page.waitForSelector(selector, { timeout: 3000 });
    return await page.$eval(selector, (el) => el.textContent.trim());
  } catch {
    return defaultValue;
  }
}
```

### 并发抓取多个页面

```js
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());

async function crawlBatch(urls, concurrency = 3) {
  const browser = await puppeteer.launch({ headless: 'new' });
  const results = [];

  // 分批并发处理
  for (let i = 0; i < urls.length; i += concurrency) {
    const batch = urls.slice(i, i + concurrency);
    const batchResults = await Promise.all(
      batch.map(async (url) => {
        const page = await browser.newPage();
        try {
          await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
          const title = await page.title();
          return { url, title, success: true };
        } catch (e) {
          return { url, error: e.message, success: false };
        } finally {
          await page.close();
        }
      })
    );
    results.push(...batchResults);
  }

  await browser.close();
  return results;
}
```

---

## 参考资源

- 官方文档：https://pptr.dev
- GitHub：https://github.com/puppeteer/puppeteer
- puppeteer-extra：https://github.com/berstend/puppeteer-extra
- stealth 插件文档：https://github.com/berstend/puppeteer-extra/tree/master/packages/puppeteer-extra-plugin-stealth
- 反检测测试页：https://bot.sannysoft.com
- Chrome DevTools Protocol：https://chromedevtools.github.io/devtools-protocol/
