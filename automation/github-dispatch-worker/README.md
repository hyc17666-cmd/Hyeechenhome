# GitHub Actions 外部定时触发器

这个 Cloudflare Worker 在每天北京时间 10:17、10:47、11:17 调用 GitHub Actions 的
`workflow_dispatch` 接口，避免完全依赖 GitHub 原生 `schedule` 的尽力而为调度。

它不会重复抓取：工作流收到 `cloudflare-cron` 触发后会先运行
`scripts/check_freshness.py`，当天数据已完整时直接跳过抓取和部署。

## 1. 创建 GitHub Token

在 GitHub 创建 fine-grained personal access token：

- Repository access：只选择 `hyc17666-cmd/Hyeechenhome`
- Permissions：`Actions: Read and write`
- 建议设置有效期，并在过期前续期

## 2. 部署 Cloudflare Worker

```powershell
cd automation/github-dispatch-worker
npm install
npx wrangler login
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put TRIGGER_SECRET
npx wrangler deploy
```

- `GITHUB_TOKEN`：上一步创建的 fine-grained PAT
- `TRIGGER_SECRET`：自定义一串足够长的随机值，只用于手动测试接口

部署完成后，Cloudflare 会自动按 `wrangler.toml` 中的 Cron Triggers 运行。

## 3. 验证

健康检查：

```text
GET https://<worker-name>.<your-subdomain>.workers.dev/health
```

手动触发一次：

```powershell
curl.exe -X POST `
  -H "Authorization: Bearer <TRIGGER_SECRET>" `
  https://<worker-name>.<your-subdomain>.workers.dev/trigger
```

然后在 GitHub 仓库的 Actions 页面确认出现了
`Update digest · workflow_dispatch · cloudflare-cron` 运行记录。

## 维护

- 如果换了 GitHub 账号或仓库，更新 `wrangler.toml` 中的 `GITHUB_REPO`。
- 修改 Cron 时间后重新执行 `npx wrangler deploy`。
- GitHub PAT 过期后，外部触发会失败；GitHub 原生 schedule 仍保留作为兜底。