# SQLite Grounded QA

一个本地可运行的自然语言问答项目：用户用中文提问，系统从 SQLite 数据库检索原文片段，将原文摘录作为证据交给大模型汇总回答。没有配置大模型 API key 时，系统会退化为本地摘录模式，仍然保证回答有据可查。

## 功能

- SQLite 文档库，内置 FTS5 全文检索。
- Web 对话界面。
- 每次回答返回数据库原文摘录和来源。
- 支持添加文档到 SQLite。
- 支持 OpenAI-compatible Chat Completions API。

## 启动

```bash
python3 app.py --seed
```

打开：

```text
http://127.0.0.1:8000
```

## 配置大模型

不配置也能运行，只是回答会使用本地摘录模式。配置后，大模型会基于检索到的原文摘录汇总回答。

```bash
export LLM_API_KEY="你的 API key"
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_MODEL="gpt-4o-mini"
python3 app.py --seed
```

如果使用其他 OpenAI-compatible 服务，修改 `LLM_BASE_URL` 和 `LLM_MODEL` 即可。

## 数据库

默认数据库文件：

```text
data/knowledge.db
```

核心表：

```sql
CREATE TABLE documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

## 测试

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Ubuntu 服务器部署

完整部署说明见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 大模型对接

千问 32B、Ollama、vLLM、OpenAI-compatible 服务的对接方式见 [MODEL_INTEGRATION.md](MODEL_INTEGRATION.md)。
