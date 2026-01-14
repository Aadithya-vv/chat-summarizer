from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

app = FastAPI()

# ----------------------------
# CORS
# ----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later you can restrict this to your Vercel domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Request Models
# ----------------------------
class SummarizeRequest(BaseModel):
    chat_text: str
    model: str = "accurate"  # fast | accurate
    last_n: int = 100        # 0 means "all"

class AskRequest(BaseModel):
    chat_text: str
    question: str
    model: str = "accurate"  # fast | accurate
    last_n: int = 100        # 0 means "all"


# ----------------------------
# PROMPTS
# ----------------------------
NORMAL_MODE_PROMPT = """
You are summarizing an informal chat conversation between people.
The conversation may include greetings, casual talk, mixed languages,
emotions, arguments, suggestions, jokes, slang, and incomplete sentences.

Your goal is to produce a helpful, human-readable summary that explains:
- what the conversation was about
- what conclusions were reached (if any)
- what the likely next steps are

The chat provided may be a recent excerpt from a much longer conversation.
Only the most recent messages are included.
Do not assume missing context from earlier parts of the chat.

GENERAL RULES:
- Do NOT invent facts that are not clearly supported by the chat.
- Do NOT include emails, passwords, phone numbers, or other sensitive data.
- Do NOT quote timestamps unless they are essential.
- Keep the tone neutral and practical.
- If context is missing, say it's unclear.

FORMAT YOUR RESPONSE EXACTLY LIKE THIS:

🧠 Main Topics
- ...

✅ Decisions
- ...

🛠 Action Items
- ...

📌 Notes / Context
- ...

Chat:
<<<
{chat_text}
>>>
""".strip()

ASK_PROMPT = """
You are answering a question about a chat conversation.

RULES:
- Answer ONLY using information present in the provided chat text.
- If the chat does not contain enough information, say:
  "Not enough context in the chat to answer that."
- Do NOT guess or invent missing context.
- Keep the answer short, clear, and direct.
- Do NOT include passwords, emails, or sensitive data.

Chat:
<<<
{chat_text}
>>>

Question:
{question}

Answer:
""".strip()


# ----------------------------
# Helpers
# ----------------------------
def get_last_n_lines(chat_text: str, n: int) -> str:
    lines = [l for l in chat_text.splitlines() if l.strip()]
    if n <= 0:
        return "\n".join(lines)
    if len(lines) <= n:
        return "\n".join(lines)
    return "\n".join(lines[-n:])


def call_ollama(model_name: str, prompt: str, max_tokens: int, temperature: float) -> str:
    url = "http://127.0.0.1:11434/api/generate"

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature
        }
    }

    r = requests.post(url, json=payload, timeout=120)

    if r.status_code != 200:
        print("❌ Ollama status:", r.status_code)
        print("❌ Ollama response:", r.text)
        r.raise_for_status()

    return r.json().get("response", "").strip()


def choose_model(mode: str):
    """
    Your installed models:
    - phi3:latest (fast)
    - mistral:latest (accurate)
    """
    if mode == "fast":
        return ("phi3:latest", 220, 0.3)
    else:
        return ("mistral:latest", 320, 0.2)


# ----------------------------
# Routes
# ----------------------------
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


@app.get("/favicon.ico")
def favicon():
    # just prevents browser 404 spam
    return {}


@app.post("/summarize")
def summarize(req: SummarizeRequest):
    try:
        chosen_model, max_tokens, temperature = choose_model(req.model)

        # cap last_n in accurate mode for speed
        if req.model == "accurate" and req.last_n > 120 and req.last_n != 0:
            req.last_n = 120

        filtered_chat = get_last_n_lines(req.chat_text, req.last_n)
        final_prompt = NORMAL_MODE_PROMPT.format(chat_text=filtered_chat)

        print(f"🧠 Summarizing | model={chosen_model} | last_n={req.last_n}")
        summary = call_ollama(chosen_model, final_prompt, max_tokens, temperature)

        return {"summary": summary}

    except Exception as e:
        print("❌ ERROR:", str(e))
        return {"summary": "❌ Error: Could not generate summary."}


@app.post("/ask")
def ask(req: AskRequest):
    try:
        if not req.question.strip():
            return {"answer": "Please type a question."}

        chosen_model, _, _ = choose_model(req.model)

        # Ask mode should be short + fast
        max_tokens = 180
        temperature = 0.2

        # cap last_n in accurate mode
        if req.model == "accurate" and req.last_n > 120 and req.last_n != 0:
            req.last_n = 120

        filtered_chat = get_last_n_lines(req.chat_text, req.last_n)
        final_prompt = ASK_PROMPT.format(chat_text=filtered_chat, question=req.question)

        print(f"💬 Ask | model={chosen_model} | last_n={req.last_n}")
        answer = call_ollama(chosen_model, final_prompt, max_tokens, temperature)

        return {"answer": answer}

    except Exception as e:
        print("❌ ERROR:", str(e))
        return {"answer": "❌ Error: Could not answer question."}
