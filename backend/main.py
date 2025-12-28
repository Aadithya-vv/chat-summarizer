from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import hashlib
import requests

# ----------------------------
# APP SETUP
# ----------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# CACHE (IN-MEMORY)
# ----------------------------
summary_cache = {}

# ----------------------------
# REQUEST MODEL
# ----------------------------
class SummarizeRequest(BaseModel):
    chat_text: str
    mode: str = "tldr"

# ----------------------------
# HASH FUNCTION
# ----------------------------
def get_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# ----------------------------
# ENDPOINT
# ----------------------------
@app.post("/summarize")
def summarize(req: SummarizeRequest):
    chat_text = req.chat_text.strip()
    if not chat_text:
        return {"summary": "", "cached": False}

    text_hash = get_text_hash(chat_text)

    # CACHE HIT
    if text_hash in summary_cache:
        print("⚡ Cache hit")
        return {"summary": summary_cache[text_hash], "cached": True}

    print("🧠 Cache miss → calling LLM")

    prompt = f"""
You must summarize the chat using EXACTLY this format.

Rules:
- Use bullet points starting with "-"
- Do NOT write paragraphs
- Do NOT leave sections empty
- If nothing exists, write "- None"

FORMAT (STRICT):

🧠 Main Topics
- item 1
- item 2

✅ Decisions
- item 1
- item 2

🛠 Action Items
- item 1
- item 2

Chat:
{chat_text}
"""

    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "mistral",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 300
                }
            },
            timeout=300
        )

        response.raise_for_status()
        result = response.json().get("response", "").strip()

        if not result:
            raise Exception("Empty LLM output")

        summary_cache[text_hash] = result
        return {"summary": result, "cached": False}

    except Exception as e:
        print("❌ ERROR:", e)
        return {
            "summary": "🧠 Main Topics\n- None\n\n✅ Decisions\n- None\n\n🛠 Action Items\n- None",
            "cached": False
        }
