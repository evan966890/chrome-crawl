# browser-use 使用指南 — browser-use Guide

browser-use 是一款具备更强页面语义理解能力的 AI 浏览器自动化工具。
与 agent-browser 相比，它能更好地理解复杂页面结构，并支持直接使用用户已有的 Chrome Profile（含所有登录态 Cookie），无需重新登录任何网站。

**核心优势**：让 AI 直接使用你已经登录好的浏览器，避免重复登录。

---

## 安装

### 方式 1：Skill Hub（推荐）

访问 Skill Hub 页面：https://www.skill-cn.com/skill/51

按照页面指引一键安装。安装完成后可在对话中直接触发。

### 方式 2：npx 命令行安装

```bash
npx skills add browser-use

# 验证安装
npx browser-use --version
```

### 方式 3：全局安装

```bash
npm install -g browser-use

# 验证
browser-use --version
```

---

## 触发方式

在与 AI 对话时，使用以下自然语言短语触发 browser-use：

```
# 中文触发
"用我的浏览器打开..."
"用浏览器帮我..."
"用我的 Chrome 登录到..."
"帮我在浏览器里填写..."

# 英文触发
"use my browser to..."
"open with my browser..."
```

---

## 使用用户自己的 Chrome Profile

这是 browser-use 相比其他工具最大的优势——直接使用你日常用的 Chrome，继承所有登录态。

### 默认 Profile（最简单）

```bash
# 直接使用默认 Chrome Profile（已登录的所有网站立即可用）
browser-use --task "打开 GitHub，查看我的 Pull Request 列表"
```

### 指定特定 Profile

Chrome 支持多个 Profile（人物/用户），可以按需选择：

```bash
# 列出所有可用 Profile
browser-use --list-profiles

# 输出示例：
# Profile 0: Default (主用户)
# Profile 1: Work (工作账号)
# Profile 2: Personal (个人账号)

# 使用指定 Profile
browser-use --profile "Default" --task "检查邮件"
browser-use --profile "Work"    --task "在公司系统里提交申请"
```

### Profile 目录路径（手动指定）

```bash
# macOS
browser-use --profile-dir "$HOME/Library/Application Support/Google/Chrome/Default" \
  --task "your task"

# Linux
browser-use --profile-dir "$HOME/.config/google-chrome/Default" \
  --task "your task"

# Windows
browser-use --profile-dir "%LOCALAPPDATA%/Google/Chrome/User Data/Default" \
  --task "your task"
```

> **注意**：使用 Profile 时需要关闭该 Profile 对应的 Chrome 窗口，Chrome 同一 Profile 不允许被两个进程同时打开。

---

## 典型使用场景

### 场景 1：复杂表单填写

```bash
# 填写需要多步骤、多字段的复杂表单
browser-use --task "
  打开 https://forms.example.com/apply
  在姓名字段填入：张三
  在邮箱字段填入：zhang@example.com
  在「所在城市」下拉框选择：上海
  在「申请原因」文本框填入：希望参与该项目以提升技术能力
  点击提交按钮
  截图保存最终结果
"
```

### 场景 2：需要登录态的自动化操作

```bash
# 使用已登录的 GitHub 账号操作（无需重新登录）
browser-use --profile "Default" --task "
  打开 https://github.com
  找到我的仓库列表
  点击 chrome-crawl 仓库
  查看最新的 Issues，返回 Issue 标题和编号
"
```

### 场景 3：微信公众号后台操作

```bash
# Chrome 已登录微信公众号后台，直接使用
browser-use --profile "Default" --task "
  打开 https://mp.weixin.qq.com
  进入素材管理
  找到草稿箱中最新的文章
  点击预览，填入手机号 13812345678 发送预览
"
```

### 场景 4：电商平台批量操作

```bash
# 使用登录态进行批量操作（手动登录过于繁琐的场景）
browser-use --profile "Default" --task "
  打开 https://seller.jd.com
  进入商品管理
  找到库存低于 10 件的商品
  将这些商品的库存批量更新为 100
"
```

### 场景 5：多步骤信息收集

```bash
# 需要跨多个页面收集信息
browser-use --task "
  打开 https://news.ycombinator.com
  获取当前 Top 10 文章的标题、链接和得分
  对每篇文章，点进去获取评论数量
  汇总返回一个 JSON 格式的结果
"
```

---

## Python API 调用

```python
from browser_use import BrowserUse

# 初始化（使用默认 Profile）
bu = BrowserUse(profile="Default")

# 执行任务
result = bu.run("""
    打开 https://example.com/dashboard
    找到今日数据报表
    截图保存
    返回页面标题和主要数据指标
""")

print(result.summary)
print(result.screenshots)  # 截图路径列表
```

### 带错误处理的用法

```python
from browser_use import BrowserUse, TaskResult
import json

bu = BrowserUse(
    profile="Default",
    timeout=120,          # 任务超时时间（秒）
    headless=False,       # 调试时设为 False 可以看到浏览器
    save_screenshots=True # 每步自动截图（便于调试）
)

try:
    result: TaskResult = bu.run("""
        打开 https://admin.example.com
        登录（如果未登录）用户名：admin
        进入用户管理页面
        导出用户列表为 CSV
        保存到 /tmp/users.csv
    """)

    if result.success:
        print(f"任务成功：{result.summary}")
    else:
        print(f"任务失败：{result.error}")
        print(f"失败截图：{result.error_screenshot}")

except TimeoutError:
    print("任务超时，请检查网络或页面加载情况")
```

---

## 与 agent-browser 的选型对比

| 维度 | agent-browser | browser-use |
|------|:---:|:---:|
| **简单任务 token 消耗** | ✅ 低（$0.76） | ⚠️ 中（$1.40） |
| **复杂任务 token 消耗** | ⚠️ 高波动（$5–16） | ✅ 较稳定（$3.76–9） |
| **复杂页面理解** | ⚠️ 一般 | ✅ 强 |
| **使用已有登录态** | ✅（Chrome Cookie） | ✅（Profile 直接使用） |
| **多步骤交互准确性** | ⚠️ 一般 | ✅ 高 |
| **操作透明度** | ✅（CLI 命令可见） | ⚠️（内部自主决策） |
| **调试便捷性** | ✅（逐命令执行） | ⚠️（需开 headless=False） |

**经验法则**：
- 任务步骤 ≤ 5 步，页面结构清晰 → agent-browser
- 任务步骤 > 5 步，或页面有动态加载/复杂交互 → browser-use
- 需要保持登录态，且不想折腾 CDP → browser-use

---

## 调试技巧

### 开启可视化模式

```bash
# 以非无头模式运行，可以看到浏览器实时操作
browser-use --headless=false --task "your task"
```

### 保存每步截图

```bash
# 保存操作过程截图到指定目录（便于排查问题）
browser-use --save-screenshots ./debug-shots --task "your task"
```

### 增大超时时间

```bash
# 复杂任务或网络慢时增大超时
browser-use --timeout 300 --task "your task"
```

### 查看详细日志

```bash
# 开启详细日志
browser-use --verbose --task "your task"
```

---

## 常见问题

**Q：Chrome Profile 被锁定（Profile is already in use）？**

关闭对应的 Chrome 窗口后重试。同一 Profile 不能被两个进程同时打开。

```bash
# 检查是否有残留 Chrome 进程占用该 Profile
ps aux | grep chrome
# 关闭相关进程
kill <PID>
```

**Q：任务执行到一半卡住了？**

开启 `--headless=false` 可视化模式观察浏览器状态：

```bash
browser-use --headless=false --timeout 60 --task "your task"
```

**Q：登录态失效（提示需要重新登录）？**

在普通 Chrome 中手动重新登录目标网站，然后重新执行任务。browser-use 会自动读取最新的 Cookie。

**Q：如何处理二步验证 / CAPTCHA？**

browser-use 遇到验证码或二步验证时会暂停并提示用户手动完成，完成后继续自动执行。这与所有浏览器自动化工具的行为一致——CAPTCHA 目前无法自动绕过。

```bash
# 启用交互模式（等待用户输入 CAPTCHA）
browser-use --interactive --task "your task"
```

---

## 参考

- browser-use Skill Hub 页面：https://www.skill-cn.com/skill/51
- 工具选型参考：见 `docs/browser-tools-comparison.md`
- agent-browser 用法：见 `SKILL.md`（浏览器 UI 自动化章节）
- pinchtab（生产/多 Agent 场景）：见 `docs/pinchtab-quickstart.md`
