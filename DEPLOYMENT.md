# Ubuntu 服务器部署说明

本文档说明如何把本项目部署到 Ubuntu 服务器，并配置为长期运行的 Web 服务。

## 1. 项目架构

```text
sqlite-grounded-qa
├── app.py                  # 后端服务：HTTP API、SQLite 检索、LLM 调用
├── README.md               # 本地开发说明
├── DEPLOYMENT.md           # Ubuntu 部署说明
├── static/
│   ├── index.html          # 前端页面
│   ├── app.js              # 前端交互逻辑
│   └── styles.css          # 前端样式
├── tests/
│   └── test_app.py         # 单元测试
└── data/
    └── knowledge.db        # SQLite 数据库，运行后自动创建
```

### 核心流程

```text
用户问题
  ↓
前端 POST /api/chat
  ↓
app.py 接收问题
  ↓
SQLite FTS5 / LIKE 检索 documents 表
  ↓
返回相关原文摘录 citations
  ↓
如果配置 LLM_API_KEY：
    把“问题 + 原文摘录”发给大模型总结
否则：
    使用本地摘录模板回答
  ↓
前端展示答案 + 数据库原文依据
```

### SQLite 表结构

```sql
CREATE TABLE documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

同时创建 `documents_fts` 虚拟表，用于全文检索。

## 2. 服务器要求

推荐环境：

```text
Ubuntu 22.04 LTS 或 Ubuntu 24.04 LTS
Python 3.10+
SQLite 3，需支持 FTS5
Nginx，可选但推荐
systemd
```

本项目当前只使用 Python 标准库，不需要安装第三方 Python 包。

## 3. 安装系统依赖

```bash
sudo apt update
sudo apt install -y git python3 python3-venv sqlite3 nginx ufw
```

检查 SQLite 是否支持 FTS5：

```bash
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect(':memory:')
conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
print("SQLite FTS5 OK")
PY
```

如果输出 `SQLite FTS5 OK`，说明环境可用。

## 4. 拉取项目

建议部署到 `/opt/sqlite-grounded-qa`：

```bash
sudo mkdir -p /opt/sqlite-grounded-qa
sudo chown -R $USER:$USER /opt/sqlite-grounded-qa
git clone https://github.com/yjh1412/git.git /opt/sqlite-grounded-qa
cd /opt/sqlite-grounded-qa
```

如果服务器没有 GitHub 权限，也可以把项目压缩包上传到该目录。

## 5. 创建运行用户

生产环境建议使用独立用户运行服务：

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin qaapp
sudo chown -R qaapp:qaapp /opt/sqlite-grounded-qa
```

确保 `data/` 目录可写：

```bash
sudo mkdir -p /opt/sqlite-grounded-qa/data
sudo chown -R qaapp:qaapp /opt/sqlite-grounded-qa/data
```

## 6. 配置环境变量

创建环境文件：

```bash
sudo nano /etc/sqlite-grounded-qa.env
```

如果暂时不接入大模型，可以写：

```bash
APP_HOST=127.0.0.1
APP_PORT=8000
```

如果接入 OpenAI 或 OpenAI-compatible 服务：

```bash
APP_HOST=127.0.0.1
APP_PORT=8000
LLM_API_KEY=你的API_KEY
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

国产或私有模型服务只要兼容 OpenAI Chat Completions API，也可以这样配置：

```bash
LLM_API_KEY=你的API_KEY
LLM_BASE_URL=https://你的模型服务地址/v1
LLM_MODEL=你的模型名称
```

保护环境文件权限：

```bash
sudo chown root:qaapp /etc/sqlite-grounded-qa.env
sudo chmod 640 /etc/sqlite-grounded-qa.env
```

## 7. 本地试运行

先用当前用户测试：

```bash
cd /opt/sqlite-grounded-qa
python3 app.py --seed --host 127.0.0.1 --port 8000
```

另开一个终端测试接口：

```bash
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"P0故障多久响应？"}'
```

确认能返回 JSON 后，按 `Ctrl+C` 停止测试服务。

## 8. 配置 systemd 服务

创建服务文件：

```bash
sudo nano /etc/systemd/system/sqlite-grounded-qa.service
```

写入：

```ini
[Unit]
Description=SQLite Grounded QA
After=network.target

[Service]
Type=simple
User=qaapp
Group=qaapp
WorkingDirectory=/opt/sqlite-grounded-qa
EnvironmentFile=/etc/sqlite-grounded-qa.env
ExecStart=/usr/bin/python3 /opt/sqlite-grounded-qa/app.py --seed --host ${APP_HOST} --port ${APP_PORT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable sqlite-grounded-qa
sudo systemctl start sqlite-grounded-qa
```

查看状态：

```bash
sudo systemctl status sqlite-grounded-qa
```

查看日志：

```bash
sudo journalctl -u sqlite-grounded-qa -f
```

## 9. 配置 Nginx 反向代理

如果你有域名，例如：

```text
qa.example.com
```

创建 Nginx 配置：

```bash
sudo nano /etc/nginx/sites-available/sqlite-grounded-qa
```

写入：

```nginx
server {
    listen 80;
    server_name qa.example.com;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/sqlite-grounded-qa /etc/nginx/sites-enabled/sqlite-grounded-qa
sudo nginx -t
sudo systemctl reload nginx
```

访问：

```text
http://qa.example.com
```

如果没有域名，可以先用服务器 IP 访问。把 `server_name` 改成：

```nginx
server_name _;
```

## 10. 配置 HTTPS

有域名时建议安装 Certbot：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d qa.example.com
```

证书续期通常由 Certbot 自动配置。可以检查：

```bash
sudo systemctl list-timers | grep certbot
```

## 11. 防火墙

如果使用 Nginx：

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

生产环境不建议直接开放 `8000` 端口。让服务只监听 `127.0.0.1:8000`，由 Nginx 对外提供 80/443。

## 12. 更新项目

```bash
cd /opt/sqlite-grounded-qa
sudo -u qaapp git pull
sudo systemctl restart sqlite-grounded-qa
```

如果当前目录权限导致 `git pull` 失败，可以临时用部署用户操作：

```bash
sudo chown -R $USER:$USER /opt/sqlite-grounded-qa
git pull
sudo chown -R qaapp:qaapp /opt/sqlite-grounded-qa
sudo systemctl restart sqlite-grounded-qa
```

## 13. 备份 SQLite 数据库

数据库默认位置：

```text
/opt/sqlite-grounded-qa/data/knowledge.db
```

备份：

```bash
sudo sqlite3 /opt/sqlite-grounded-qa/data/knowledge.db ".backup '/opt/sqlite-grounded-qa/data/knowledge-$(date +%F).db'"
```

恢复：

```bash
sudo systemctl stop sqlite-grounded-qa
sudo cp /opt/sqlite-grounded-qa/data/knowledge-YYYY-MM-DD.db /opt/sqlite-grounded-qa/data/knowledge.db
sudo chown qaapp:qaapp /opt/sqlite-grounded-qa/data/knowledge.db
sudo systemctl start sqlite-grounded-qa
```

## 14. 常见问题

### 端口被占用

```bash
sudo lsof -i :8000
sudo systemctl restart sqlite-grounded-qa
```

也可以修改 `/etc/sqlite-grounded-qa.env`：

```bash
APP_PORT=8001
```

然后：

```bash
sudo systemctl restart sqlite-grounded-qa
```

### 没有调用大模型

检查环境变量：

```bash
sudo systemctl show sqlite-grounded-qa --property=Environment
sudo journalctl -u sqlite-grounded-qa -n 100
```

确认 `/etc/sqlite-grounded-qa.env` 中包含：

```bash
LLM_API_KEY=...
LLM_BASE_URL=...
LLM_MODEL=...
```

### GitHub 拉取失败

服务器没有 GitHub 权限时，可以使用 HTTPS 公共仓库地址。如果仓库改成私有，需要配置 SSH key 或 GitHub token。

### SQLite 权限错误

确认运行用户能写入 `data/`：

```bash
sudo chown -R qaapp:qaapp /opt/sqlite-grounded-qa/data
sudo systemctl restart sqlite-grounded-qa
```

