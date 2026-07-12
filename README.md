<p align="center">
  <img src=".github/assets/banner.svg" alt="V2EX 每日自动签到" width="100%">
</p>

<p align="center">
  <a href="https://github.com/dotracel/checkin-v2ex/actions/workflows/docker-publish.yml"><img src="https://github.com/dotracel/checkin-v2ex/actions/workflows/docker-publish.yml/badge.svg" alt="Build"></a>
  <a href="https://github.com/dotracel/checkin-v2ex/pkgs/container/checkin-v2ex"><img src="https://img.shields.io/badge/ghcr.io-checkin--v2ex-2496ED?logo=docker&logoColor=white" alt="Docker Image"></a>
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white" alt="Python">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-34d399" alt="License"></a>
</p>

# V2EX 每日签到

自动领取 V2EX 每日登录奖励，并可选推送结果通知。使用 Docker 部署，配置好 Cookie 即可每天自动签到。

## 快速开始

1. 新建一个目录，创建 `docker-compose.yml`：

   ```yaml
   services:
     v2ex-checkin:
       image: ghcr.io/dotracel/checkin-v2ex:latest
       container_name: v2ex-checkin
       restart: unless-stopped
       environment:
         RUN_MODE: daemon
         CHECKIN_TIME: "08:30"
         TZ: Asia/Shanghai
       env_file:
         - .env
   ```

2. 在同一目录创建 `.env`，填入你的配置（见下方[配置说明](#配置说明)）：

   ```dotenv
   V2EX_COOKIE=A2="..."; A2O="..."; PB3_SESSION="..."; V2EX_LANG=zhcn
   APPRISE_URLS=
   ```

3. 启动：

   ```bash
   docker compose up -d
   ```

   容器会常驻运行，每天 `CHECKIN_TIME`（默认 08:30）自动签到。

## 配置说明

| 变量 | 必填 | 说明 |
|------|:---:|------|
| `V2EX_COOKIE` | ✅ | 浏览器里的完整 Cookie 字符串，**必须包含 `A2` 和 `A2O`** |
| `APPRISE_URLS` | | 通知地址，多个用逗号或换行分隔；留空则只写日志 |
| `CHECKIN_TIME` | | 每天签到时间 `HH:MM`，默认 `08:30` |
| `TZ` | | 时区，默认 `Asia/Shanghai` |

### 如何获取 Cookie

登录 v2ex.com → 打开浏览器开发者工具 → Network → 点击对 `www.v2ex.com` 的请求 → 在 Request Headers 里复制整段 `cookie` 的值，粘贴到 `V2EX_COOKIE`。确保包含 `A2` 和 `A2O`。

> Cookie 会长期有效但并非永久。失效后签到会失败并推送提醒，重新复制一次 Cookie 即可。

### 通知配置

`APPRISE_URLS` 支持 [Apprise](https://github.com/caronc/apprise/wiki) 的上百种服务，例如：

```
tgram://<bot_token>/<chat_id>      # Telegram
bark://<device_key>@api.day.app    # Bark（iOS）
wecombot://<key>                   # 企业微信机器人
```

飞书等更多服务见 Apprise 文档。

## 常用命令

```bash
docker compose logs -f      # 查看日志
docker compose pull         # 更新到最新镜像
docker compose up -d        # 应用配置改动 / 重启
docker compose down         # 停止并移除容器
```
