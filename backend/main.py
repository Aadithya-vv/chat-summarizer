from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import re

app = FastAPI()

# ✅ CORS (frontend access)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Models
# -----------------------------
class SummarizeRequest(BaseModel):
    chat_text: str
    model: str = "accurate"   # fast | accurate
    last_n: int = 0           # 0 = all

class AskRequest(BaseModel):
    chat_text: str
    summary: str = ""
    question: str
    model: str = "accurate"   # fast | accurate

# -----------------------------
# Helpers
# -----------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"

MODEL_MAP = {
    "fast": "phi3:latest",
    "accurate": "mistral:latest"
}

def clean_chat(chat_text: str) -> str:
    # remove WhatsApp encryption banner line if present
    chat_text = re.sub(r"Messages and calls are end-to-end encrypted.*", "", chat_text, flags=re.IGNORECASE)
    return chat_text.strip()

def keep_last_n_messages(chat_text: str, last_n: int) -> str:
    """
    Keep last N WhatsApp-style messages (NOT last N lines).
    A new message usually starts like:
    [18:45, 02/01/2026] Name: message
    """
    if last_n <= 0:
        return chat_text

    lines = chat_text.splitlines()

    # pattern: [time, date] Name:
    msg_start = re.compile(r"^\[\d{1,2}:\d{2},\s\d{2}/\d{2}/\d{4}\]\s.+?:\s")

    messages = []
    current = []

    for line in lines:
        if msg_start.match(line.strip()):
            # save previous message
            if current:
                messages.append("\n".join(current).strip())
                current = []
        current.append(line)

    # last message
    if current:
        messages.append("\n".join(current).strip())

    # If parsing fails, fallback to original
    if len(messages) == 0:
        return chat_text

    return "\n".join(messages[-last_n:])


def ollama_generate(model_name: str, prompt: str, max_tokens: int = 250) -> str:
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.3
        }
    }

    r = requests.post(OLLAMA_URL, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    return data.get("response", "").strip()

# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def root():
    return {
        "status": "✅ Backend is running",
        "endpoints": {
            "docs": "/docs",
            "summarize": "POST /summarize",
            "ask": "POST /ask"
        }
    }

@app.post("/summarize")
def summarize(req: SummarizeRequest):
    chat_text = clean_chat(req.chat_text or "")
    if not chat_text.strip():
        return {"summary": ""}

    model_name = MODEL_MAP.get(req.model, MODEL_MAP["accurate"])
    chat_text = keep_last_n_messages(chat_text, req.last_n)

    prompt = f"""
You are summarizing an informal chat conversation between people.
The conversation may include greetings, casual talk, mixed languages,
emotions, arguments, suggestions, and incomplete sentences.

Your goal is to produce a helpful, human-readable summary that explains:
- what the conversation was about
- what conclusions were reached (if any)
- what the likely next steps are

Follow these rules carefully:

GENERAL RULES:
- Do NOT invent facts that are not supported by the chat.
- Do NOT include emails, passwords, phone numbers, or other sensitive data.
- Do NOT quote timestamps unless they clearly matter.
- Keep the tone neutral and practical.
- It is okay to infer reasonable next steps if they are strongly implied.
- If a detail is unclear (like "uninstall it"), do NOT assume what "it" refers to.

SECTION RULES:

1. Main Topics:
   - List 3–6 key themes discussed.
   - Topics should be high-level and human-friendly.

2. Decisions:
   - Include explicit decisions or clear conclusions.
   - If no clear decisions were made, write "None".

3. Action Items:
   - Include explicit tasks AND strongly implied next steps.
   - Do NOT assign blame.
   - Use short, clear bullet points.

4. Notes / Context:
   - Add helpful background, conditions, or missing context.
   - If something is unclear, mention it here instead of guessing.

FORMAT YOUR RESPONSE EXACTLY LIKE THIS:

🧠 Main Topics
- ...

✅ Decisions
- ...

🛠 Action Items
- ...

📌 Notes / Context
- ...

CHAT:
{chat_text}
""".strip()

    try:
        summary = ollama_generate(model_name, prompt, max_tokens=320)
        return {"summary": summary}
    except Exception as e:
        print("❌ /summarize ERROR:", repr(e))
        return {"summary": "Error: Could not generate summary."}

@app.post("/ask")
def ask(req: AskRequest):
    chat_text = clean_chat(req.chat_text or "")
    summary = (req.summary or "").strip()
    question = (req.question or "").strip()

    if not chat_text.strip():
        return {"answer": "Please paste the chat first."}

    if not question:
        return {"answer": "Please type a question."}

    model_name = MODEL_MAP.get(req.model, MODEL_MAP["accurate"])

    prompt = f"""
You are an assistant helping a user understand a WhatsApp chat.

Answer the user's question using ONLY what is present in the chat text.
If the chat does NOT contain enough info, do NOT guess.
Reply naturally like a helpful human:

- Start with what the chat DOES show.
- If the answer is not confirmed, say: "From this chat alone..."
- Suggest what extra message/context would help.
- Keep it short (1–4 lines).
- Do NOT reveal emails/passwords/phone numbers.

CHAT:
{chat_text}

SUMMARY:
{summary}

USER QUESTION:
{question}

Answer naturally:
""".strip()

    try:
        answer = ollama_generate(model_name, prompt, max_tokens=180)
        if not answer.strip():
            return {"answer": "I couldn't find a clear answer in this chat. Can you paste a few more messages?"}
        return {"answer": answer}
    except Exception as e:
        print("❌ /ask ERROR:", repr(e))
        return {"answer": f"Error while answering: {str(e)}"}
