# 三报今日 · 聚合网页

北京日报、光明日报、经济日报的每日标题聚合页。项目只保存标题、栏目、日期和原文链接，不保存或公开转载正文，避免未经授权传播全文。

## 功能

- 三报标题聚合；
- 按报纸、日期、栏目筛选；
- 标题关键词搜索；
- 每日北京时间 10:00 自动更新；
- GitHub Pages 免费公网发布；
- 来源失败时保留旧数据，不影响其他来源；
- 最近 30 天数据保留。

## 目录

```text
three-papers-aggregator/
├─ scraper.py                  # 三报标题采集器
├─ requirements.txt
├─ site/
│  ├─ index.html               # 聚合页
│  ├─ assets/styles.css
│  ├─ assets/app.js
│  └─ data/articles.json       # 自动生成的数据
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

## 发布公网地址

1. 在 GitHub 新建仓库，例如 `three-papers-daily`；
2. 将本目录推送到 `main` 分支；
3. 打开仓库 `Settings → Pages`；
4. 在 `Build and deployment` 中选择 `GitHub Actions`；
5. 打开 `Actions → Update and deploy three-paper digest → Run workflow`；
6. 部署完成后地址为：

```text
https://你的用户名.github.io/three-papers-daily/
```

## 更新时间

工作流中的定时表达式：

```yaml
cron: "0 2 * * *"
```

GitHub Actions 使用 UTC，`02:00 UTC` 对应北京时间 `10:00`。定时任务可能有几分钟延迟，这是 GitHub 平台调度机制决定的。

## 版权说明

本站是标题导航和原文链接聚合，不转载文章正文。文章版权归原报刊及作者所有。若要在公网展示全文，请先取得北京日报、光明日报、经济日报或相应权利人的授权。

## 维护提示

三报电子报页面结构可能调整。如果某个来源连续失败：

1. 检查对应电子报当日页面是否可以访问；
2. 检查 `scraper.py` 中该来源的版面链接和标题选择器；
3. 运行 `python scraper.py --date YYYY-MM-DD --verbose` 查看日志；
4. 确认 GitHub Actions 运行环境能访问三报网站。
