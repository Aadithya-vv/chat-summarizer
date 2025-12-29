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
    model: str = "accurate"  # "fast" or "accurate"

# ----------------------------
# HASH FUNCTION
# ----------------------------
def get_cache_key(text: str, model: str) -> str:
    combined = f"{model}:{text}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()

# ----------------------------
# MODEL MAP
# ----------------------------
MODEL_MAP = {
    "fast": "phi3",
    "accurate": "mistral"
}

# ----------------------------
# ENDPOINT
# ----------------------------
@app.post("/summarize")
def summarize(req: SummarizeRequest):
    chat_text = req.chat_text.strip()
    model_choice = req.model.lower()

    if not chat_text:
        return {"summary": "", "cached": False}

    if model_choice not in MODEL_MAP:
        model_choice = "accurate"

    ollama_model = MODEL_MAP[model_choice]

    cache_key = get_cache_key(chat_text, model_choice)

    # CACHE HIT
    if cache_key in summary_cache:
        print(f"⚡ Cache hit ({model_choice})")
        return {
            "summary": summary_cache[cache_key],
            "cached": True
        }

    print(f"🧠 Cache miss → model={ollama_model}")

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
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2 if model_choice == "accurate" else 0.3,
                    "num_predict": 200 if model_choice == "fast" else 300
                }
            },
            timeout=300
        )

        response.raise_for_status()
        result = response.json().get("response", "").strip()

        if not result:
            raise Exception("Empty LLM response")

        summary_cache[cache_key] = result

        return {
            "summary": result,
            "cached": False
        }

    except Exception as e:
        print("❌ ERROR:", e)
        return {
            "summary": "🧠 Main Topics\n- None\n\n✅ Decisions\n- None\n\n🛠 Action Items\n- None",
            "cached": False
        }
