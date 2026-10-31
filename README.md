# 三报一刊 · 聚合网页

“三报一刊”每日标题聚合页：人民日报、光明日报、经济日报、求是。

- 在线地址：https://hyc17666-cmd.github.io/Hyeechenhome/
- GitHub 仓库：https://github.com/hyc17666-cmd/Hyeechenhome

项目只保存标题、栏目、日期、期号和原文链接，不保存或公开转载正文，避免未经授权传播全文。

## 功能

- 人民日报、光明日报、经济日报、求是四家来源聚合；
- 按报刊、日期、栏目筛选；
- 标题关键词搜索；
- 每天北京时间 10:17 起自动更新，10:47、11:17、11:47 自动补跑；
- 可配置 Cloudflare Worker 在 10:17 主动触发 GitHub Actions；
- 自动化运行在 GitHub/Cloudflare 服务器上，不依赖本地 Codex 或电脑是否开机；
- GitHub Pages 免费公网发布；
- 某个来源失败时保留旧数据，不影响其他来源；
- 报纸保留最近 30 天数据，求是只保留当前期。

## 来源

- 人民日报电子报
- 光明日报电子报
- 经济日报电子报
- 求是网当期杂志

求是是半月刊，因此网页把它作为“当前期”展示；卡片底部显示期号，例如 `2026/20`，而不是强行套用日报日期。

## 目录

```text
three-papers-one-journal/
├─ scraper.py                  # 三报一刊标题采集器
├─ requirements.txt
├─ site/
│  ├─ index.html               # 聚合页
│  ├─ assets/styles.css
│  ├─ assets/app.js
│  └─ data/articles.json       # 自动生成的数据
├─ automation/github-dispatch-worker/  # 可选的外部定时触发器
└─ .github/workflows/
   └─ update-and-deploy.yml    # 每日更新并发布 GitHub Pages
```

## 本地运行

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scraper.py
python -m http.server 8765 --directory site
```

浏览器打开：

```text
http://localhost:8765
```

采集指定日期：

```powershell
python scraper.py --date 2026-10-29
```

## 更新时间

GitHub Actions 使用 UTC。原生定时任务现在保留四个补跑窗口：

```yaml
schedule:
  - cron: "17 2 * * *"  # 北京时间 10:17
  - cron: "47 2 * * *"  # 北京时间 10:47
  - cron: "17 3 * * *"  # 北京时间 11:17
  - cron: "47 3 * * *"  # 北京时间 11:47
```

但 GitHub 原生 `schedule` 是尽力而为调度，负载高时可能延迟，严重时任务可能被丢弃。因此要实现每天 10:17 主动更新，建议同时部署仓库自带的外部定时触发器：

```text
automation/github-dispatch-worker/
```

Cloudflare Worker 会使用 GitHub `workflow_dispatch` 在以下时间触发：

- 北京时间 10:17（主触发）
- 北京时间 10:47（重试）
- 北京时间 11:17（兜底）

每次触发都会先运行 `scripts/check_freshness.py`。当天数据已完整时会直接跳过，不会重复抓取、提交或部署。

### 外部触发器配置

1. 在 GitHub 创建 fine-grained PAT：
   - 只授权 `hyc17666-cmd/Hyeechenhome`
   - 权限选择 `Actions: Read and write`
2. 进入外部触发器目录并部署：

```powershell
cd automation/github-dispatch-worker
npm install
npx wrangler login
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put TRIGGER_SECRET
npx wrangler deploy
```

详细说明见 `automation/github-dispatch-worker/README.md`。外部触发器部署后，日常更新不需要打开 Codex，也不需要电脑保持开机。

## 版权说明

本站是标题导航和原文链接聚合，不转载文章正文。文章版权归原报刊及作者所有。若要在公网展示全文，请先取得人民日报、光明日报、经济日报、求是或相应权利人的授权。

## 维护提示

报刊电子报页面结构可能调整。如果某个来源连续失败：

1. 检查对应电子报当日页面是否可以访问；
2. 检查 `scraper.py` 中该来源的版面链接和标题选择器；
3. 运行 `python scraper.py --date YYYY-MM-DD --verbose` 查看日志；
4. 确认 GitHub Actions 运行环境能访问对应报刊网站。
