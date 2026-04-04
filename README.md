# 每日重点新闻邮件推送项目

一个独立的 `Python` 项目，用来每天抓取多源新闻、用 `OpenAI 兼容接口` 做中文总结，并通过 `HTML 邮件` 自动发送简报。

## 功能

- 聚合 `官方发布页 / Reuters / Federal Reserve / 定向 Google News 发现器`
- 仅抓取最近 `24` 小时候选新闻
- 规则去重：`URL` 去重、标题近似去重、来源压缩
- AI 多段流水线：候选清洗、事件聚合、总编终审、最终写稿
- 输出编辑筛选后的中文简报：`今日主线 + 今日重点 + 新闻速览 + 今日关注点 + 原文链接`
- 条数不是固定值，按当天真正值得看的新闻动态输出
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
OPENAI_REASONING_EFFORT
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
$env:OPENAI_REASONING_EFFORT="high"
$env:SMTP_HOST="smtp.qq.com"
$env:SMTP_PORT="465"
$env:SMTP_USER="your@qq.com"
$env:SMTP_PASS="qq邮箱授权码"
$env:MAIL_FROM="your@qq.com"
$env:MAIL_TO="2401991251@qq.com,2291678383@qq.com,2249518071@qq.com,3421720690@qq.com"
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

当前默认策略不是泛泛抓取，而是偏向：

- 国内：政策、重大民生、公共事件、科技、财经、市场变化
- 国际：头部公司、重大市场、重大地缘事件、货币政策
- 明确剔除：地方小事、校园活动、会展论坛、营销软文、普通小公司动态、二手搬运内容

默认上限是 `8` 条今日重点 + `16` 条新闻速览，只有在当天确实有足够重要事件时才会发满。

当前信源采用冻结版治理结构：

- `official`：政府、央媒、官方机构
- `media`：高质量媒体
- `discovery`：发现器，只负责补漏
- `tier`：`S / A / B`，决定 source 在评分、代表稿与国内参考中的优先级

每个 source 都带有 `fetcher / parser / tier / role`，用于决定：

- 如何抓取
- 如何解析
- 代表稿如何选
- 国内参考如何补
- 在终稿里能占到多高优先级

## GitHub Actions

工作流文件位于：

- [daily-news.yml](/D:/OneDrive/Desktop/cherry项目/daily-news-briefing/.github/workflows/daily-news.yml)

计划任务默认每天 `08:00` 以 `Asia/Shanghai` 时区运行，同时支持手动触发：

- 手动预览
- 手动正式发送
- 手动发送测试邮件

工作流会在正式发送成功后提交 `state/seen_events.json` 的变化。

工作流运行后会在 GitHub Actions Summary 中展示：

- 总候选数、去重后数量、清洗后数量
- 事件聚合数、终审事件数
- 今日重点 / 新闻速览 / 今日关注点条数
- 命中的官方源数量
- 带 `国内参考` 的条目数量
- `Google News` 仍作为最终主链接的条目数量
- `lead` 区各主题家族分布
- 每个 source 的候选数
- `zero-hit source` 列表
- 健康警告，例如“某个官方源今日未产出候选”

## 新建独立 GitHub 仓库

这个项目按“独立新仓库”交付，推荐直接把 `daily-news-briefing` 目录单独建仓。

1. 在 GitHub 创建一个新的空仓库，例如 `daily-news-briefing`
2. 把当前目录 [daily-news-briefing](/D:/OneDrive/Desktop/cherry项目/daily-news-briefing) 作为仓库根目录推上去
3. 在仓库 `Settings -> Secrets and variables -> Actions` 中配置这些 Secrets：
   - `OPENAI_BASE_URL`
   - `OPENAI_API_KEY`
   - `OPENAI_MODEL`
   - `OPENAI_REASONING_EFFORT`
   - `SMTP_HOST`
   - `SMTP_PORT`
   - `SMTP_USER`
   - `SMTP_PASS`
   - `MAIL_FROM`
   - `MAIL_TO`
4. 手动触发 Actions 的 `preview / send-test / run` 三种模式做首轮验证
5. 确认 `run` 成功后，仓库里 `state/seen_events.json` 会被自动提交更新

推荐首次上线前检查 [seen_events.json](/D:/OneDrive/Desktop/cherry项目/daily-news-briefing/state/seen_events.json)：

- 如果希望 GitHub 上线后的第一天从空状态开始，建议先将其重置为空基线内容
- 如果希望保留当前本地发送历史，也可以直接沿用现有状态文件

关于 Actions Summary：

- `zero-hit source` 代表该 source 当天候选数为 0，不一定表示系统失败，但值得观察
- `Google News 主链接数 > 0` 表示某些最终条目仍没有更优原始链接或国内参考可替代
- `命中官方源数` 越高，通常代表当天国内政策与公共事件覆盖更稳
- `lead 家族分布` 用于确认前排没有被同一类新闻刷屏

## 说明

- 正文提取采用标准库实现，遇到反爬或正文提取失败时会自动回退到 `RSS 摘要 + 标题`。
- `OpenAI 兼容接口` 默认按 `chat/completions` 风格调用，以兼容常见的 OpenAI 格式 API。
- 即使 `LLM` 调用失败，仍有规则回退路径，项目不会直接中断。
- 邮件里不再展示模板化的“为什么重要”，而是直接给重点标题、来源和高密度摘要。
- 国际链接有时会落到聚合页或海外媒体页，但这不会影响摘要质量；来源权重高于链接可达性。
