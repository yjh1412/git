# 大模型对接方案

本文档说明如何用最少代码改动对接服务器上的 MiniMax-M3、千问 32B 等模型，并为以后切换其他模型保留统一方案。

## 1. 推荐原则

本项目后端已经使用 OpenAI-compatible Chat Completions API：

```text
POST {LLM_BASE_URL}/chat/completions
```

因此推荐让任何本地或远程大模型都统一暴露为 OpenAI-compatible 接口。项目代码不需要为每个模型分别适配，只需要修改环境变量：

```bash
LLM_API_KEY=任意非空值或真实 key
LLM_BASE_URL=http://127.0.0.1:8001/v1
LLM_MODEL=模型名称
```

当前代码读取位置：

```python
base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
model = os.getenv("LLM_MODEL", "gpt-4o-mini")
```

## 2. 接入 MiniMax-M3

MiniMax-M3 推荐作为本地模型服务运行，并通过 OpenAI-compatible API 暴露给本项目。这样不需要为 MiniMax 单独写一套调用代码。

### 2.1 启动 MiniMax-M3 OpenAI-compatible 服务

如果你的服务器已经部署好了 MiniMax-M3，只需要确认它能提供类似接口：

```text
http://127.0.0.1:8001/v1/chat/completions
```

如果使用 vLLM，并且模型在本地路径 `/models/MiniMax-M3`，可以按下面方式启动：

```bash
source /opt/vllm-venv/bin/activate
vllm serve /models/MiniMax-M3 \
  --host 127.0.0.1 \
  --port 8001 \
  --served-model-name minimax-m3
```

如果模型服务已经由其他团队部署，只要拿到三项信息即可：

```text
base_url: http://模型服务地址/v1
model: 模型名称，例如 minimax-m3
api_key: 如果本地服务不校验，可用 local
```

### 2.2 测试 MiniMax-M3 接口

```bash
curl http://127.0.0.1:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local" \
  -d '{
    "model": "minimax-m3",
    "messages": [
      {"role": "user", "content": "用一句话介绍你自己"}
    ],
    "temperature": 0.2
  }'
```

能返回 `choices[0].message.content`，说明 MiniMax-M3 可以被本项目直接调用。

### 2.3 配置本项目使用 MiniMax-M3

编辑：

```bash
sudo nano /etc/sqlite-grounded-qa.env
```

写入：

```bash
APP_HOST=127.0.0.1
APP_PORT=8000
LLM_API_KEY=local
LLM_BASE_URL=http://127.0.0.1:8001/v1
LLM_MODEL=minimax-m3
```

重启项目：

```bash
sudo systemctl restart sqlite-grounded-qa
```

本项目现在对本地 `127.0.0.1` / `localhost` 模型服务做了容错：如果忘记设置 `LLM_API_KEY`，会自动使用 `local` 作为占位 token。生产环境对公网模型服务仍然应该配置真实 key。

## 3. vLLM 部署千问 32B

如果服务器有 NVIDIA GPU，推荐用 vLLM。vLLM 原生提供 OpenAI-compatible API，和本项目最匹配。

### 3.1 安装 vLLM

建议先创建 Python 虚拟环境：

```bash
python3 -m venv /opt/vllm-venv
source /opt/vllm-venv/bin/activate
pip install --upgrade pip
pip install vllm
```

### 3.2 启动 Qwen 32B

示例一：使用 Hugging Face 模型名：

```bash
source /opt/vllm-venv/bin/activate
vllm serve Qwen/Qwen2.5-32B-Instruct \
  --host 127.0.0.1 \
  --port 8001 \
  --served-model-name qwen32b
```

示例二：使用本地模型路径：

```bash
source /opt/vllm-venv/bin/activate
vllm serve /models/Qwen2.5-32B-Instruct \
  --host 127.0.0.1 \
  --port 8001 \
  --served-model-name qwen32b
```

如果显存不足，可根据服务器情况使用量化模型，或调整 vLLM 参数。常见方向：

```bash
--tensor-parallel-size 2
--gpu-memory-utilization 0.90
--max-model-len 8192
```

多卡时示例：

```bash
vllm serve /models/Qwen2.5-32B-Instruct \
  --host 127.0.0.1 \
  --port 8001 \
  --served-model-name qwen32b \
  --tensor-parallel-size 2
```

### 3.3 测试 vLLM 接口

```bash
curl http://127.0.0.1:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local" \
  -d '{
    "model": "qwen32b",
    "messages": [
      {"role": "user", "content": "用一句话介绍你自己"}
    ],
    "temperature": 0.2
  }'
```

能返回 `choices[0].message.content` 即可对接本项目。

### 3.4 配置本项目

编辑：

```bash
sudo nano /etc/sqlite-grounded-qa.env
```

写入：

```bash
APP_HOST=127.0.0.1
APP_PORT=8000
LLM_API_KEY=local
LLM_BASE_URL=http://127.0.0.1:8001/v1
LLM_MODEL=qwen32b
```

重启项目服务：

```bash
sudo systemctl restart sqlite-grounded-qa
```

查看日志：

```bash
sudo journalctl -u sqlite-grounded-qa -f
```

## 4. 使用 Ollama 对接千问

如果服务器用 Ollama 管理模型，也可以对接。Ollama 提供 OpenAI-compatible API。

### 4.1 安装并启动模型

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:32b
ollama serve
```

Ollama 默认监听：

```text
http://127.0.0.1:11434
```

OpenAI-compatible base URL 为：

```text
http://127.0.0.1:11434/v1
```

### 4.2 配置本项目

```bash
APP_HOST=127.0.0.1
APP_PORT=8000
LLM_API_KEY=ollama
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen2.5:32b
```

然后：

```bash
sudo systemctl restart sqlite-grounded-qa
```

## 5. 使用 DashScope / 阿里云百炼

如果不在本机跑模型，而是使用阿里云百炼的兼容 OpenAI 接口，配置类似：

```bash
APP_HOST=127.0.0.1
APP_PORT=8000
LLM_API_KEY=你的DashScope或百炼API_KEY
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
```

具体模型名以服务商控制台为准。

## 6. 以后切换其他模型

只要新模型服务兼容 OpenAI Chat Completions API，就只改这三项：

```bash
LLM_API_KEY=...
LLM_BASE_URL=...
LLM_MODEL=...
```

例如：

```bash
# 本地 vLLM
LLM_API_KEY=local
LLM_BASE_URL=http://127.0.0.1:8001/v1
LLM_MODEL=qwen32b

# 本地 MiniMax-M3
LLM_API_KEY=local
LLM_BASE_URL=http://127.0.0.1:8001/v1
LLM_MODEL=minimax-m3

# Ollama
LLM_API_KEY=ollama
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen2.5:32b

# OpenAI
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini

# 其他兼容服务
LLM_API_KEY=服务商API_KEY
LLM_BASE_URL=https://服务商地址/v1
LLM_MODEL=服务商模型名
```

业务代码不用改。

## 7. 推荐的生产架构

```text
浏览器
  ↓
Nginx 80/443
  ↓
sqlite-grounded-qa
  127.0.0.1:8000
  ↓
SQLite
  data/knowledge.db
  ↓
OpenAI-compatible LLM
  127.0.0.1:8001/v1    # vLLM
  或 127.0.0.1:11434/v1 # Ollama
  或云厂商 /v1
```

推荐只让 Nginx 对公网开放。SQLite QA 服务和大模型服务都监听 `127.0.0.1`，避免直接暴露到公网。

## 8. systemd 管理 vLLM

MiniMax-M3 示例：

```bash
sudo nano /etc/systemd/system/minimax-m3-vllm.service
```

```ini
[Unit]
Description=MiniMax-M3 vLLM OpenAI API
After=network.target

[Service]
Type=simple
User=qaapp
Group=qaapp
WorkingDirectory=/opt/sqlite-grounded-qa
Environment=CUDA_VISIBLE_DEVICES=0
ExecStart=/opt/vllm-venv/bin/vllm serve /models/MiniMax-M3 --host 127.0.0.1 --port 8001 --served-model-name minimax-m3
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable minimax-m3-vllm
sudo systemctl start minimax-m3-vllm
sudo journalctl -u minimax-m3-vllm -f
```

千问 32B 示例：

创建：

```bash
sudo nano /etc/systemd/system/qwen32b-vllm.service
```

写入：

```ini
[Unit]
Description=Qwen 32B vLLM OpenAI API
After=network.target

[Service]
Type=simple
User=qaapp
Group=qaapp
WorkingDirectory=/opt/sqlite-grounded-qa
Environment=CUDA_VISIBLE_DEVICES=0
ExecStart=/opt/vllm-venv/bin/vllm serve /models/Qwen2.5-32B-Instruct --host 127.0.0.1 --port 8001 --served-model-name qwen32b
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable qwen32b-vllm
sudo systemctl start qwen32b-vllm
sudo journalctl -u qwen32b-vllm -f
```

启动成功后，再启动本项目：

```bash
sudo systemctl restart sqlite-grounded-qa
```

## 9. 如何确认已经用上大模型

在页面提问后，如果后端成功调用大模型，接口返回：

```json
{
  "used_llm": true
}
```

如果返回：

```json
{
  "used_llm": false
}
```

说明没有成功调用大模型，系统退回到了本地摘录模式。

也可以直接用接口测试：

```bash
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"P0故障多久响应？"}'
```

## 10. 排查顺序

1. 大模型服务是否能直接访问：

```bash
curl http://127.0.0.1:8001/v1/models \
  -H "Authorization: Bearer local"
```

2. `LLM_BASE_URL` 是否包含 `/v1`：

```bash
LLM_BASE_URL=http://127.0.0.1:8001/v1
```

3. `LLM_MODEL` 是否等于服务端暴露的模型名：

```bash
LLM_MODEL=qwen32b
```

4. 项目服务是否加载了环境变量：

```bash
sudo systemctl restart sqlite-grounded-qa
sudo journalctl -u sqlite-grounded-qa -n 100
```

5. 不要把大模型服务直接暴露到公网，除非额外加鉴权、限流和 HTTPS。
