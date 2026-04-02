# 每日重点新闻邮件推送项目

一个独立的 `Python` 项目，用来每天抓取多源新闻、用 `OpenAI 兼容接口` 做中文总结，并通过 `HTML 邮件` 自动发送简报。

## 功能

- 聚合 `Google News RSS / Reuters / TechCrunch / 36Kr`
- 仅抓取最近 `24` 小时候选新闻
- 规则去重：`URL` 去重、标题近似去重、来源压缩
- AI 三段流水线：候选清洗、事件聚合、最终写稿
- 输出固定结构：`今日判断 + 6 条核心头条 + 6 条快讯 + 原文链接`
- 推送主通道为 `QQ 邮箱 SMTP`
- 支持 `GitHub Actions` 定时运行和手动触发
- 通过 `state/seen_events.json` 避免连续几天重复推送同一事件

## 目录结构

```text
daily-news-briefing/
├─ .github/workflows/daily-news.yml
├─ config.yaml
├─ state/seen_events.json
├─ src/daily_news_briefing/
├─ tests/
└─ README.md
```

## 环境要求

- `Python 3.11+`
- 一个 `OpenAI 兼容接口`
- 一个可用于发送邮件的 `QQ 邮箱 SMTP` 账号

## 必需环境变量

```text
OPENAI_BASE_URL
OPENAI_API_KEY
OPENAI_MODEL
SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_PASS
MAIL_FROM
MAIL_TO
```

推荐的 `QQ 邮箱 SMTP` 默认值：

```text
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
```

说明：

- `SMTP_PASS` 应填写 `QQ 邮箱授权码`，不是登录密码。
- `MAIL_TO` 支持多个收件人，用英文逗号或分号分隔。

## 快速开始

1. 进入项目目录：

```powershell
cd D:\OneDrive\Desktop\cherry项目\daily-news-briefing
```

2. 配置环境变量。

3. 运行预览：

```powershell
$env:PYTHONPATH="src"
$env:OPENAI_BASE_URL="https://your-openai-compatible-api/v1"
$env:OPENAI_API_KEY="sk-xxxx"
$env:OPENAI_MODEL="gpt-4.1-mini"
$env:SMTP_HOST="smtp.qq.com"
$env:SMTP_PORT="465"
$env:SMTP_USER="your@qq.com"
$env:SMTP_PASS="qq邮箱授权码"
$env:MAIL_FROM="your@qq.com"
$env:MAIL_TO="your@qq.com"
python -m daily_news_briefing.cli preview
```

4. 正式发送：

```powershell
$env:PYTHONPATH="src"
python -m daily_news_briefing.cli run
```

5. 仅测试邮件通道：

```powershell
$env:PYTHONPATH="src"
python -m daily_news_briefing.cli send-test
```

## 本地测试

当前项目默认不要求先执行 `pip install -e .`。本地测试和运行统一使用 `PYTHONPATH=src`：

```powershell
cd D:\OneDrive\Desktop\cherry项目\daily-news-briefing
$env:PYTHONPATH="src"
python -m compileall src/daily_news_briefing
python -m unittest discover -s tests -v
```

## 命令说明

- `run`：抓取、总结、发送，并更新已发送状态
- `preview`：抓取、总结、生成本地 `HTML` 预览，不发送
- `send-test`：只发送测试邮件，验证 `SMTP`

## 配置说明

非敏感配置写在 [config.yaml](/D:/OneDrive/Desktop/cherry项目/daily-news-briefing/config.yaml)。

`config.yaml` 虽然使用 `.yaml` 扩展名，但当前采用 `JSON 兼容 YAML` 写法，便于在没有第三方依赖的环境下直接读取。

## GitHub Actions

工作流文件位于：

- [daily-news.yml](/D:/OneDrive/Desktop/cherry项目/daily-news-briefing/.github/workflows/daily-news.yml)

计划任务默认每天 `08:00` 以 `Asia/Shanghai` 时区运行，同时支持手动触发：

- 手动预览
- 手动正式发送
- 手动发送测试邮件

工作流会在正式发送成功后提交 `state/seen_events.json` 的变化。

## 新建独立 GitHub 仓库

这个项目按“独立新仓库”交付，推荐直接把 `daily-news-briefing` 目录单独建仓。

1. 在 GitHub 创建一个新的空仓库，例如 `daily-news-briefing`
2. 把当前目录 [daily-news-briefing](/D:/OneDrive/Desktop/cherry项目/daily-news-briefing) 作为仓库根目录推上去
3. 在仓库 `Settings -> Secrets and variables -> Actions` 中配置这些 Secrets：
   - `OPENAI_BASE_URL`
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL`
   - `SMTP_HOST`
   - `SMTP_PORT`
   - `SMTP_USER`
   - `SMTP_PASS`
   - `MAIL_FROM`
   - `MAIL_TO`
4. 手动触发 Actions 的 `preview / send-test / run` 三种模式做首轮验证
5. 确认 `run` 成功后，仓库里 `state/seen_events.json` 会被自动提交更新

## 说明

- 正文提取采用标准库实现，遇到反爬或正文提取失败时会自动回退到 `RSS 摘要 + 标题`。
- `OpenAI 兼容接口` 默认按 `chat/completions` 风格调用，以兼容常见的 OpenAI 格式 API。
- 即使 `LLM` 调用失败，仍有规则回退路径，项目不会直接中断。
