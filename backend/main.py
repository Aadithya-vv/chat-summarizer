from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import re
from collections import Counter
from datetime import datetime

app = FastAPI()

# ✅ CORS MUST be added right after app creation
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # you can restrict later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Fix preflight OPTIONS requests (important for browsers)
@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str):
    return {}

# -----------------------------
# Request Models
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

class AnalyticsRequest(BaseModel):
    chat_text: str
    last_n: int = 0

# -----------------------------
# Ollama Settings
# -----------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"

MODEL_MAP = {
    "fast": "phi3:latest",
    "accurate": "mistral:latest"
}

# -----------------------------
# Stopwords (basic)
# -----------------------------
STOPWORDS = set("""
a an the and or but if then else so because as at by for from in into on onto out over under to of
is am are was were be been being do does did doing have has had having
i me my mine we us our ours you your yours he him his she her hers they them their theirs
this that these those it its it's im i'm u ur ya bro dude man
ok okay hmm lol lmao bruh
""".split())

# Extra junk words we never want in top words
JUNK_WORDS = set("""
am pm a.m p.m
jan january feb february mar march apr april may jun june jul july aug august sep september oct october nov november dec december
""".split())

# -----------------------------
# Helpers
# -----------------------------
def clean_chat(chat_text: str) -> str:
    chat_text = chat_text.strip()
    chat_text = re.sub(r"Messages and calls are end-to-end encrypted.*", "", chat_text, flags=re.IGNORECASE)
    return chat_text.strip()

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

# WhatsApp formats
PATTERN_BRACKET = re.compile(
    r"^\[(\d{1,2}:\d{2}),\s(\d{2}/\d{2}/\d{4})\]\s(.+?):\s(.*)$"
)
PATTERN_DASH = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{2,4}),\s(\d{1,2}:\d{2})\s-\s(.+?):\s(.*)$"
)

def parse_whatsapp_messages(chat_text: str):
    lines = chat_text.splitlines()
    messages = []
    current = None

    def push_current():
        nonlocal current
        if current:
            current["text"] = current["text"].strip()
            if current["text"]:
                messages.append(current)
        current = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        m1 = PATTERN_BRACKET.match(line)
        m2 = PATTERN_DASH.match(line)

        if m1:
            push_current()
            time_str, date_str, user, text = m1.groups()

            dt = None
            try:
                dt = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
            except:
                dt = None

            current = {
                "datetime": dt,
                "date_str": date_str,
                "time_str": time_str,
                "user": user.strip(),
                "text": text.strip()
            }

        elif m2:
            push_current()
            date_str, time_str, user, text = m2.groups()

            dt = None
            try:
                if len(date_str.split("/")[-1]) == 2:
                    dt = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%y %H:%M")
                else:
                    dt = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
            except:
                dt = None

            current = {
                "datetime": dt,
                "date_str": date_str,
                "time_str": time_str,
                "user": user.strip(),
                "text": text.strip()
            }

        else:
            if current:
                current["text"] += "\n" + raw.strip()
            else:
                current = {
                    "datetime": None,
                    "date_str": "",
                    "time_str": "",
                    "user": "Unknown",
                    "text": raw.strip()
                }

    push_current()
    return messages

def keep_last_n_messages(chat_text: str, last_n: int) -> str:
    if last_n <= 0:
        return chat_text

    msgs = parse_whatsapp_messages(chat_text)
    if not msgs:
        return chat_text

    last_msgs = msgs[-last_n:]
    out = []
    for m in last_msgs:
        if m["date_str"] and m["time_str"]:
            out.append(f"[{m['time_str']}, {m['date_str']}] {m['user']}: {m['text']}")
        else:
            out.append(f"{m['user']}: {m['text']}")
    return "\n".join(out)

def extract_emojis(text: str):
    emoji_pattern = re.compile(
        "[" 
        "\U0001F300-\U0001F5FF"
        "\U0001F600-\U0001F64F"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\u2600-\u26FF"
        "\u2700-\u27BF"
        "]+",
        flags=re.UNICODE
    )
    return emoji_pattern.findall(text)

def tokenize_words(text: str):
    text = text.lower()

    # remove links
    text = re.sub(r"http\S+", "", text)

    # remove timestamps like 18:45
    text = re.sub(r"\b\d{1,2}:\d{2}\b", " ", text)

    # remove dates like 02/01/2026 or 2/1/26
    text = re.sub(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", " ", text)

    # remove pure numbers
    text = re.sub(r"\b\d+\b", " ", text)

    # keep only words (letters + apostrophe)
    tokens = re.findall(r"[a-z']+", text)

    # remove stopwords + junk words + tiny tokens
    tokens = [
        t for t in tokens
        if t not in STOPWORDS
        and t not in JUNK_WORDS
        and len(t) > 1
    ]

    return tokens

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
            "ask": "POST /ask",
            "analytics": "POST /analytics"
        }
    }

@app.post("/summarize")
def summarize(req: SummarizeRequest):
    chat_text = clean_chat(req.chat_text or "")
    if not chat_text.strip():
        return {"summary": ""}

    model_name = MODEL_MAP.get(req.model, MODEL_MAP["accurate"])
    chat_text = keep_last_n_messages(chat_text, req.last_n)

    if len(chat_text.strip()) < 30:
        return {"summary": "Not enough recent messages to summarize. Try a bigger number or paste more chat."}

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

Reply naturally:
- Start with what the chat DOES show.
- If unsure say: "From this chat alone..."
- Keep it short (1–4 lines).

CHAT:
{chat_text}

SUMMARY:
{summary}

USER QUESTION:
{question}

Answer:
""".strip()

    try:
        answer = ollama_generate(model_name, prompt, max_tokens=180)
        if not answer.strip():
            return {"answer": "I couldn't find a clear answer in this chat. Paste a few more messages."}
        return {"answer": answer}
    except Exception as e:
        print("❌ /ask ERROR:", repr(e))
        return {"answer": "Sorry, I couldn’t answer that right now. Try again."}

@app.post("/analytics")
def analytics(req: AnalyticsRequest):
    chat_text = clean_chat(req.chat_text or "")
    if not chat_text.strip():
        return {
            "total_messages": 0,
            "messages_per_user": {},
            "most_active_day": None,
            "most_active_hour": None,
            "top_words_mode": "repeated",
            "top_words": [],
            "top_emojis": []
        }

    messages = parse_whatsapp_messages(chat_text)

    if req.last_n and req.last_n > 0 and len(messages) > req.last_n:
        messages = messages[-req.last_n:]

    total_messages = len(messages)

    per_user = Counter()
    per_day = Counter()
    per_hour = Counter()
    word_counter = Counter()
    emoji_counter = Counter()

    # ✅ Collect participant names to exclude them from top words
    participants = set()
    for m in messages:
        if m.get("user"):
            participants.add(m["user"].strip().lower())

    participant_tokens = set()
    for name in participants:
        parts = re.findall(r"[a-z']+", name.lower())
        for p in parts:
            if len(p) > 1:
                participant_tokens.add(p)

    for m in messages:
        user = m.get("user", "Unknown") or "Unknown"
        text = m.get("text", "") or ""

        per_user[user] += 1

        dt = m.get("datetime")
        if dt:
            per_day[dt.strftime("%Y-%m-%d")] += 1
            per_hour[str(dt.hour).zfill(2)] += 1

        # words
        for w in tokenize_words(text):
            if w in participant_tokens:
                continue
            word_counter[w] += 1

        # emojis
        for em in extract_emojis(text):
            emoji_counter[em] += 1

    most_active_day = per_day.most_common(1)[0][0] if per_day else None
    most_active_hour = per_hour.most_common(1)[0][0] if per_hour else None

    # ✅ 1) Try repeated words first (count >= 2)
    repeated_words = [(w, c) for w, c in word_counter.items() if c >= 2]
    repeated_words.sort(key=lambda x: x[1], reverse=True)

    if len(repeated_words) > 0:
        top_words_mode = "repeated"
        top_words = [{"word": w, "count": c} for w, c in repeated_words[:10]]
    else:
        # ✅ 2) Fallback to normal top words (count >= 1)
        top_words_mode = "fallback"
        top_words = [{"word": w, "count": c} for w, c in word_counter.most_common(10)]

    top_emojis = [{"emoji": e, "count": c} for e, c in emoji_counter.most_common(10)]

    return {
        "total_messages": total_messages,
        "messages_per_user": dict(per_user),
        "most_active_day": most_active_day,
        "most_active_hour": most_active_hour,
        "top_words_mode": top_words_mode,
        "top_words": top_words,
        "top_emojis": top_emojis
    }

