from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

app = FastAPI()

# ----------------------------
# CORS (IMPORTANT for frontend)
# ----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later restrict to your vercel domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Request Model
# ----------------------------
class SummarizeRequest(BaseModel):
    chat_text: str
    model: str = "accurate"  # fast | accurate
    last_n: int = 100        # 50 | 100 | 300


# ----------------------------
# Prompt (NORMAL MODE)
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
- Do NOT assume knowledge from outside the provided messages.
- Do NOT include emails, passwords, phone numbers, or other sensitive data.
- Do NOT quote timestamps unless they are essential.
- Keep the tone neutral and practical.
- It is acceptable to infer reasonable next steps ONLY if strongly implied.
- When context is missing, prefer uncertainty over specificity.

IMPORTANT AMBIGUITY RULE:
- If an action refers to vague terms like "it", "that", "this",
  and the object is not clearly defined in the chat,
  do NOT guess it. Keep it abstract or mark as unclear.

SECTION RULES:

1. Main Topics:
   - List 3–6 high-level themes.

2. Decisions:
   - Include explicit decisions or conclusions.
   - If none, write exactly: "None".

3. Action Items:
   - Include explicit tasks and strongly implied next steps.
   - Do NOT assign ownership unless clearly stated.
   - Do NOT invent tasks based on assumptions.
   - Do NOT include explanations or uncertainty notes in Action Items.

4. Notes / Context:
   - Capture missing background, unclear references, or dependencies here.

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


# ----------------------------
# Helper: last N lines filter
# ----------------------------
def get_last_n_lines(chat_text: str, n: int) -> str:
    lines = [l for l in chat_text.splitlines() if l.strip()]
    if n <= 0:
        return "\n".join(lines)
    if len(lines) <= n:
        return "\n".join(lines)
    return "\n".join(lines[-n:])


# ----------------------------
# Ollama call (FAST + LIMITED)
# ----------------------------
def call_ollama(model_name: str, prompt: str, max_tokens: int, temperature: float) -> str:
    url = "http://127.0.0.1:11434/api/generate"

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,     # LIMIT OUTPUT LENGTH = HUGE SPEED BOOST
            "temperature": temperature     # LOWER = more direct, less rambling
        }
    }

    r = requests.post(url, json=payload, timeout=120)

    # debug if something fails
    if r.status_code != 200:
        print("❌ Ollama status:", r.status_code)
        print("❌ Ollama response:", r.text)
        r.raise_for_status()

    data = r.json()
    return data.get("response", "").strip()


# ----------------------------
# Route
# ----------------------------
@app.post("/summarize")
def summarize(req: SummarizeRequest):
    try:
        # ----------------------------
        # MODEL SELECTION (YOUR INSTALLED MODELS)
        # ----------------------------
        if req.model == "fast":
            chosen_model = "phi3:latest"
            max_tokens = 250
            temperature = 0.3
        else:
            chosen_model = "mistral:latest"
            max_tokens = 350
            temperature = 0.2

            # 🔥 SPEED FIX: cap last_n in accurate mode
            if req.last_n > 120:
                req.last_n = 120

        # ----------------------------
        # Filter chat to recent part
        # ----------------------------
        filtered_chat = get_last_n_lines(req.chat_text, req.last_n)

        # ----------------------------
        # Build final prompt
        # ----------------------------
        final_prompt = NORMAL_MODE_PROMPT.format(chat_text=filtered_chat)

        print(f"🧠 Summarizing using model={chosen_model} | last_n={req.last_n} | max_tokens={max_tokens}")

        summary = call_ollama(
            model_name=chosen_model,
            prompt=final_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )

        return {"summary": summary}

    except Exception as e:
        print("❌ ERROR:", str(e))
        return {"summary": "❌ Error: Could not generate summary."}
