# OKX 交易脚本迁移到 Ubuntu 服务器

服务器：`154.222.31.222`，Ubuntu 22.04，SSH 端口 `22`。

## 1. OKX API 白名单

至少加入：

```text
154.222.31.222
```

API 只开交易权限，不开提现权限。

## 2. 上传代码

第一次可以带 `.env`：

```powershell
.\scripts\deploy_to_server.ps1 -HostName 154.222.31.222 -User root -Port 22 -IncludeEnv
```

以后改代码但不覆盖密钥：

```powershell
.\scripts\deploy_to_server.ps1 -HostName 154.222.31.222 -User root -Port 22
```

## 3. 初始化服务器并安装服务

SSH 到服务器：

```powershell
ssh root@154.222.31.222 -p 22
```

服务器执行：

```bash
bash /opt/okx-quant/scripts/server_setup.sh
bash /opt/okx-quant/scripts/install_services.sh
```

## 4. 检查 `.env`

服务器：

```bash
nano /opt/okx-quant/.env
```

实盘需要：

```text
OKX_SIMULATED_TRADING=0
OKX_ENABLE_LIVE_TRADING=1
OKX_PROXY=
```

## 5. 测试 OKX 网络和认证

```bash
cd /opt/okx-quant
sudo -u okxbot .venv/bin/python test_okx_connection.py
curl -s -w "\nconnect=%{time_connect} tls=%{time_appconnect} total=%{time_total}\n" https://www.okx.com/api/v5/public/time
```

## 6. 启动 dashboard

```bash
systemctl start okx-dashboard
systemctl status okx-dashboard --no-pager
```

本地用 SSH 隧道访问，不要开放 8765 公网端口：

```powershell
ssh -L 8765:127.0.0.1:8765 root@154.222.31.222 -p 22
```

浏览器打开：

```text
http://127.0.0.1:8765
```

如需用域名查看，只暴露只读面板，不要把完整 dashboard 暴露到公网。步骤见：

```text
READONLY_DOMAIN.md
```

只读入口默认是：

```text
https://你的域名/view
```

## 7. 启动/停止机器人

默认由 dashboard 启动和托管 BEAT/RE 机器人。此模式下 `okx-dashboard.service`
会是 systemd 中的主服务，两个机器人会显示为 dashboard 的子进程；`okx-beat-bot`
和 `okx-re-bot` standalone unit 保持 `disabled/inactive` 是正常状态。

日常启动/停止：

1. 打开 dashboard：`http://127.0.0.1:8765`
2. 使用页面里的 BEAT/RE 启动、停止、应用参数按钮。
3. 查看日志：

```bash
tail -f /opt/okx-quant/data/okx/grid_bot_stdout.log
tail -f /opt/okx-quant/data/okx/re_grid_bot_stdout.log
```

应急或明确需要脱离 dashboard 托管时，才直接启动 standalone systemd unit。启动前先确认 dashboard 没有同交易对的子进程在运行，避免重复下单：

```bash
ps -eo pid,ppid,cmd | grep auto_grid_bot.py
```

BEAT：

```bash
systemctl start okx-beat-bot
systemctl status okx-beat-bot --no-pager
tail -f /opt/okx-quant/data/okx/grid_bot_stdout.log
```

RE：

```bash
systemctl start okx-re-bot
systemctl status okx-re-bot --no-pager
tail -f /opt/okx-quant/data/okx/re_grid_bot_stdout.log
```

停止：

```bash
systemctl stop okx-beat-bot
systemctl stop okx-re-bot
```

## 8. 排查

```bash
journalctl -u okx-dashboard -n 80 --no-pager
journalctl -u okx-beat-bot -n 80 --no-pager
journalctl -u okx-re-bot -n 80 --no-pager
```
