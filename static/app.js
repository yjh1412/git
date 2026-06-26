const chat = document.querySelector("#chat");
const chatForm = document.querySelector("#chatForm");
const messageInput = document.querySelector("#message");
const docForm = document.querySelector("#docForm");
const docs = document.querySelector("#docs");
const refreshDocs = document.querySelector("#refreshDocs");

const history = [];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function addMessage(role, text, citations = [], usedLlm = false) {
  const wrap = el("article", `message ${role}`);
  const body = el("div", "", text);
  wrap.appendChild(body);

  if (role === "assistant") {
    const mode = usedLlm ? "LLM 汇总" : "本地摘录模式";
    wrap.appendChild(el("div", "citation", `回答模式：${mode}`));
  }

  citations.forEach((item, index) => {
    const citation = el(
      "div",
      "citation",
      `[${index + 1}] ${item.title}\n来源：${item.source || "未填写"}\n原文：${item.excerpt}`
    );
    wrap.appendChild(citation);
  });

  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求失败");
  return data;
}

async function loadDocs() {
  const response = await fetch("/api/documents");
  const data = await response.json();
  docs.innerHTML = "";
  if (!data.length) {
    docs.appendChild(el("div", "empty", "还没有文档。可以先写入文档，或用 --seed 启动示例数据。"));
    return;
  }
  data.forEach((item) => {
    const node = el("div", "doc");
    node.appendChild(el("strong", "", item.title));
    node.appendChild(el("span", "", item.source || "未填写来源"));
    node.appendChild(el("span", "", `${item.content_length} 字符 · ${item.created_at}`));
    docs.appendChild(node);
  });
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;

  addMessage("user", message);
  history.push({ role: "user", content: message });
  messageInput.value = "";

  const submit = chatForm.querySelector("button");
  submit.disabled = true;
  try {
    const data = await postJson("/api/chat", { message, history: history.slice(-8) });
    addMessage("assistant", data.answer, data.citations, data.used_llm);
    history.push({ role: "assistant", content: data.answer });
  } catch (error) {
    addMessage("assistant", `请求失败：${error.message}`);
  } finally {
    submit.disabled = false;
    messageInput.focus();
  }
});

docForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    title: document.querySelector("#docTitle").value,
    source: document.querySelector("#docSource").value,
    content: document.querySelector("#docContent").value,
  };
  const submit = docForm.querySelector("button");
  submit.disabled = true;
  try {
    await postJson("/api/documents", payload);
    docForm.reset();
    await loadDocs();
  } catch (error) {
    alert(error.message);
  } finally {
    submit.disabled = false;
  }
});

refreshDocs.addEventListener("click", loadDocs);

addMessage(
  "assistant",
  "请输入问题。系统会先从 SQLite 检索原文，再基于检索结果回答；每次回答都会附带原文摘录。"
);
loadDocs();

