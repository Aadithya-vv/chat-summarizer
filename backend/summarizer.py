import requests

# Ollama local API endpoint
OLLAMA_URL = "http://localhost:11434/api/generate"


def chunk_text(text, max_lines=100):
    """
    Split very long chats into large chunks
    (used only when chat is extremely long)
    """
    lines = text.split("\n")
    chunks = []

    for i in range(0, len(lines), max_lines):
        chunks.append("\n".join(lines[i:i + max_lines]))

    return chunks


def call_llm(prompt: str) -> str:
    """
    Call local Ollama model with speed-optimized settings
    """
    payload = {
        "model": "mistral",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,   # very low randomness = faster
            "num_predict": 150,   # hard limit on output tokens
            "top_p": 0.9
        }
    }

    response = requests.post(OLLAMA_URL, json=payload, timeout=300)
    response.raise_for_status()
    return response.json()["response"].strip()


def summarize_chat(text: str, mode: str) -> str:
    """
    Main summarization pipeline

    FAST PATH:
    - If chat <= 120 lines → single LLM call (very fast)

    SLOW PATH:
    - If chat > 120 lines → chunk + merge (still optimized)
    """

    lines = text.split("\n")

    # ---------------- FAST PATH ----------------
    if len(lines) <= 120:
        prompt = f"""
You are given a group chat conversation.

Extract ONLY the following.
Be concise. Use bullet points only.

🧠 Main Topics (max 3)
✅ Decisions (max 3)
🛠 Action Items (max 5)

Ignore greetings, emojis, jokes, and filler messages.

Chat:
{text}
"""
        return call_llm(prompt)

    # ---------------- SLOW PATH ----------------
    chunks = chunk_text(text)
    chunk_summaries = []

    for chunk in chunks:
        chunk_prompt = f"""
Summarize the following group chat in 3 very short bullet points.
Ignore greetings, emojis, and casual replies.

Chat:
{chunk}

Bullets:
"""
        summary = call_llm(chunk_prompt)
        chunk_summaries.append(summary)

    final_prompt = f"""
From the summaries below, extract ONLY:

🧠 Main Topics (max 3)
✅ Decisions (max 3)
🛠 Action Items (max 5)

Be concise. Bullet points only.

Summaries:
{chr(10).join(chunk_summaries)}
"""
    return call_llm(final_prompt)
