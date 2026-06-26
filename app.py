from __future__ import annotations

import argparse
import html
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "knowledge.db"
STATIC_DIR = ROOT / "static"

MAX_CONTEXT_CHARS = 9000
MAX_EXCERPT_CHARS = 700


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    with connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              title TEXT NOT NULL,
              source TEXT NOT NULL DEFAULT '',
              content TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
            USING fts5(title, source, content, content='documents', content_rowid='id');

            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
              INSERT INTO documents_fts(rowid, title, source, content)
              VALUES (new.id, new.title, new.source, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
              INSERT INTO documents_fts(documents_fts, rowid, title, source, content)
              VALUES('delete', old.id, old.title, old.source, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
              INSERT INTO documents_fts(documents_fts, rowid, title, source, content)
              VALUES('delete', old.id, old.title, old.source, old.content);
              INSERT INTO documents_fts(rowid, title, source, content)
              VALUES (new.id, new.title, new.source, new.content);
            END;
            """
        )


def seed_demo_data(db_path: Path = DB_PATH) -> None:
    init_db(db_path)
    demo_docs = [
        (
            "公司报销制度",
            "internal://finance/reimbursement-policy",
            "员工发生差旅、办公用品、客户拜访等合理业务支出后，应在费用发生后30日内提交报销申请。"
            "单笔金额超过人民币5000元的支出，需要直属负责人和财务负责人共同审批。"
            "餐饮招待费用应写明客户名称、参与人员、业务目的，并上传发票和支付凭证。"
            "不符合业务相关性、凭证缺失、超过时限且无合理说明的费用，财务可以退回申请。",
        ),
        (
            "客户支持 SLA",
            "internal://support/sla",
            "P0 级故障是指核心系统不可用或大量客户无法使用关键功能，响应时间为15分钟内，"
            "目标恢复时间为4小时内。P1 级故障是指关键功能受影响但存在临时绕行方案，响应时间为1小时内，"
            "目标恢复时间为1个工作日内。所有故障处理记录应包含发现时间、影响范围、根因分析、恢复动作和复盘结论。",
        ),
        (
            "产品数据口径",
            "internal://product/metrics",
            "活跃用户指在统计周期内至少完成一次登录、查询、创建、编辑或导出操作的去重用户。"
            "试用账号、内部测试账号和被禁用账号不计入活跃用户。留存率按照首日使用用户在第7日或第30日再次发生有效行为计算。"
            "收入类指标以已确认订单金额为准，退款订单应在发生退款的统计周期内冲减。",
        ),
    ]
    with connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        if count:
            return
        conn.executemany(
            "INSERT INTO documents(title, source, content) VALUES (?, ?, ?)",
            demo_docs,
        )


def tokenize(text: str) -> list[str]:
    raw_terms = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
    terms: list[str] = []
    for term in raw_terms:
        if len(term) <= 1:
            continue
        if re.fullmatch(r"\d+", term):
            terms.append(term)
            continue
        if re.search(r"[\u4e00-\u9fff]", term) and len(term) > 2:
            terms.append(term)
            terms.extend([term[i : i + 2] for i in range(0, len(term) - 1)])
        else:
            terms.append(term)
    return terms[:12]


def fts_query(message: str) -> str:
    terms = tokenize(message)
    escaped = [term.replace('"', '""') for term in terms]
    return " OR ".join(f'"{term}"' for term in escaped) if escaped else '""'


def make_excerpt(content: str, query: str) -> str:
    terms = tokenize(query)
    position = -1
    lowered = content.lower()
    for term in terms:
        found = lowered.find(term.lower())
        if found >= 0:
            position = found
            break
    if position < 0:
        position = 0
    start = max(position - 180, 0)
    end = min(start + MAX_EXCERPT_CHARS, len(content))
    excerpt = content[start:end].strip()
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(content):
        excerpt += "..."
    return excerpt


def retrieve(message: str, limit: int = 5, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    init_db(db_path)
    query = fts_query(message)
    with connect(db_path) as conn:
        try:
            rows = conn.execute(
                """
                SELECT d.id, d.title, d.source, d.content, bm25(documents_fts) AS score
                FROM documents_fts
                JOIN documents d ON d.id = documents_fts.rowid
                WHERE documents_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if not rows:
            rows = retrieve_like(conn, message, limit)

    return [
        {
            "id": row["id"],
            "title": row["title"],
            "source": row["source"],
            "excerpt": make_excerpt(row["content"], message),
            "score": row["score"],
        }
        for row in rows
    ]


def retrieve_like(conn: sqlite3.Connection, message: str, limit: int) -> list[sqlite3.Row]:
    like_terms = tokenize(message)[:5]
    if not like_terms:
        like_terms = [message]
    where = " OR ".join(["content LIKE ? OR title LIKE ?" for _ in like_terms])
    params: list[Any] = []
    for term in like_terms:
        params.extend([f"%{term}%", f"%{term}%"])
    return conn.execute(
        f"SELECT id, title, source, content, 0 AS score FROM documents WHERE {where} LIMIT ?",
        (*params, limit),
    ).fetchall()


def build_prompt(message: str, citations: list[dict[str, Any]], history: list[dict[str, str]]) -> str:
    history_text = "\n".join(
        f"{item.get('role', 'user')}: {item.get('content', '')}" for item in history[-6:]
    )
    context_lines = []
    total = 0
    for index, item in enumerate(citations, start=1):
        line = (
            f"[{index}] 标题: {item['title']}\n"
            f"来源: {item['source']}\n"
            f"原文摘录: {item['excerpt']}"
        )
        total += len(line)
        if total > MAX_CONTEXT_CHARS:
            break
        context_lines.append(line)
    return (
        "你是一个基于数据库检索结果回答问题的助手。只使用给定原文摘录回答；"
        "如果摘录不足以回答，明确说明无法从当前数据库确认。回答要包含简短结论、依据引用和总结。\n\n"
        f"历史对话:\n{history_text or '无'}\n\n"
        f"用户问题:\n{message}\n\n"
        "数据库检索结果:\n"
        + "\n\n".join(context_lines)
    )


def call_llm(prompt: str) -> str | None:
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        if base_url.startswith(("http://127.0.0.1", "http://localhost")):
            api_key = "local"
        else:
            return None
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你必须基于提供的数据库原文摘录作答，并保留引用编号。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return None
    return data["choices"][0]["message"]["content"].strip()


def fallback_answer(message: str, citations: list[dict[str, Any]]) -> str:
    if not citations:
        return "当前 SQLite 数据库没有检索到足够相关的原文，无法给出有据可查的答案。"
    lines = ["根据当前 SQLite 数据库检索结果，可以参考以下依据："]
    for index, item in enumerate(citations, start=1):
        lines.append(f"[{index}] {item['title']}：{item['excerpt']}")
    lines.append("总结：以上回答仅基于已检索到的原文摘录；如需更完整结论，请补充更多数据库文档。")
    return "\n\n".join(lines)


def answer(message: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    history = history or []
    citations = retrieve(message)
    prompt = build_prompt(message, citations, history)
    llm_answer = call_llm(prompt)
    return {
        "answer": llm_answer or fallback_answer(message, citations),
        "citations": citations,
        "used_llm": bool(llm_answer),
    }


def list_documents(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, title, source, created_at, length(content) AS content_length "
            "FROM documents ORDER BY id DESC LIMIT 100"
        ).fetchall()
    return [dict(row) for row in rows]


def add_document(title: str, source: str, content: str, db_path: Path = DB_PATH) -> int:
    title = title.strip()
    source = source.strip()
    content = content.strip()
    if not title or not content:
        raise ValueError("title and content are required")
    init_db(db_path)
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO documents(title, source, content) VALUES (?, ?, ?)",
            (title, source, content),
        )
        return int(cursor.lastrowid)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, status: int, data: dict[str, Any] | list[dict[str, Any]]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            self.serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if self.path == "/styles.css":
            self.serve_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if self.path == "/app.js":
            self.serve_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if self.path == "/api/documents":
            self.send_json(200, list_documents())
            return
        self.send_error(404)

    def do_POST(self) -> None:
        try:
            if self.path == "/api/chat":
                payload = self.read_json()
                message = str(payload.get("message", "")).strip()
                history = payload.get("history") or []
                if not message:
                    self.send_json(400, {"error": "message is required"})
                    return
                self.send_json(200, answer(message, history))
                return
            if self.path == "/api/documents":
                payload = self.read_json()
                doc_id = add_document(
                    str(payload.get("title", "")),
                    str(payload.get("source", "")),
                    str(payload.get("content", "")),
                )
                self.send_json(201, {"id": doc_id})
                return
            self.send_error(404)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})

    def serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="SQLite grounded LLM QA service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--seed", action="store_true", help="insert demo documents when database is empty")
    args = parser.parse_args()

    init_db()
    if args.seed:
        seed_demo_data()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving on http://{html.escape(args.host)}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
