# OKX Quant Readonly Domain

这个入口只给域名访问“可视面板数据”，不提供启动、停止、下单、改参数等控制能力。

默认不需要登录。公网访问者只要知道域名就能看到权益、持仓、挂单、成交等只读数据，所以建议使用不容易猜到的子域名，例如 `panel-xxxx.example.com`。

## What It Runs

- Full dashboard: `127.0.0.1:8765`
- Read-only proxy: `127.0.0.1:8770`
- Public domain: points to Nginx, then Nginx proxies only to `127.0.0.1:8770`

The read-only proxy allows only:

- `GET /view`
- `GET /view.html`
- `GET /view.js`
- `GET /view.css`
- `GET /api/snapshot`
- `GET /api/bot/status`
- `GET /api/re-bot/status`
- `GET /api/bot/config`
- `GET /api/re-bot/config`

All POST/PUT/PATCH/DELETE requests are rejected.

## 1. Start The No-Login Readonly Proxy

On the server:

```bash
sudo tee /etc/okx-dashboard-readonly.env >/dev/null <<'EOF'
READONLY_DASHBOARD_HOST=127.0.0.1
READONLY_DASHBOARD_PORT=8770
READONLY_DASHBOARD_TARGET_HOST=127.0.0.1
READONLY_DASHBOARD_TARGET_PORT=8765
READONLY_DASHBOARD_AUTH_REQUIRED=false
EOF

sudo chmod 600 /etc/okx-dashboard-readonly.env
```

Install and start the service:

```bash
cd /opt/okx-quant
sudo bash scripts/install_services.sh
sudo systemctl enable --now okx-dashboard-readonly-proxy.service
sudo systemctl status okx-dashboard-readonly-proxy.service --no-pager
```

Local check on the server:

```bash
curl -I http://127.0.0.1:8770/view
curl -i -X POST http://127.0.0.1:8770/api/bot/stop
curl -i http://127.0.0.1:8770/app.js
```

Expected result:

- `/view` returns `200`
- `POST /api/bot/stop` returns `405`
- `/app.js` returns `403`

## 2. Alibaba Cloud DNS

In Alibaba Cloud:

1. Open Alibaba Cloud Console.
2. Go to 云解析 DNS.
3. Open 公网权威解析.
4. Click your domain.
5. Click 解析设置.
6. Click 添加记录.

Add this record:

```text
记录类型: A
主机记录: panel
解析请求来源: 默认
记录值: 154.222.31.222
TTL: 10 分钟
```

If you use `panel.example.com`, the 主机记录 is only `panel`, not the full domain. Alibaba Cloud automatically appends the main domain.

If your server is in mainland China, website access normally requires ICP filing. If the server is overseas, ICP filing is usually not required for this dashboard route.

## 3. Nginx + HTTPS

Replace `panel.example.com` with your real subdomain.

```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx

sudo ufw allow 80/tcp || true
sudo ufw allow 443/tcp || true
```

Create the Nginx site:

```bash
sudo tee /etc/nginx/sites-available/okx-readonly >/dev/null <<'EOF'
server {
    listen 80;
    server_name panel.example.com;

    location / {
        limit_except GET HEAD {
            deny all;
        }

        proxy_pass http://127.0.0.1:8770;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/okx-readonly /etc/nginx/sites-enabled/okx-readonly
sudo nginx -t
sudo systemctl reload nginx
```

Issue HTTPS certificate:

```bash
sudo certbot --nginx -d panel.example.com
```

Open:

```text
https://panel.example.com/view
```

## Optional: Turn Login Back On Later

If you later want a browser password, change `/etc/okx-dashboard-readonly.env`:

```bash
READONLY_DASHBOARD_AUTH_REQUIRED=true
READONLY_DASHBOARD_AUTH_USER=your_login_name
READONLY_DASHBOARD_AUTH_PASSWORD=change_this_long_password
```

Then restart:

```bash
sudo systemctl restart okx-dashboard-readonly-proxy.service
```

## Safety Notes

- Do not expose `127.0.0.1:8765` through a public domain.
- Do not open `8770` directly to the public internet.
- Public traffic should go to Nginx on 80/443, then Nginx should proxy to `127.0.0.1:8770`.
- The full dashboard should stay behind SSH tunnel or a private VPN.
