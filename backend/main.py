from fastapi import FastAPI, Request
from fastapi.responses import Response
from pydantic import BaseModel
import os

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

import warnings
import requests
import re
from collections import Counter
import numpy as np

from sklearn.feature_extraction.text import TfidfVectorizer

warnings.filterwarnings(
    "ignore",
    message="Could not find the number of physical cores.*",
    category=UserWarning,
)

app = FastAPI()


@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )

    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


class SummarizeRequest(BaseModel):
    chat_text: str
    model: str = "accurate"
    last_n: int = 0
    mode: str = "normal"
    evidence: bool = True


class AskRequest(BaseModel):
    chat_text: str
    question: str
    summary: str = ""
    model: str = "accurate"


class AnalyticsRequest(BaseModel):
    chat_text: str
    last_n: int = 0


class TopicsRequest(BaseModel):
    chat_text: str
    max_topics: int = 6
    last_n: int = 0
    chunk_size: int = 200
    sample_per_topic: int = 3
    model: str = "fast"


TOPIC_STOPWORDS = {
    "aadithya", "aadhitya", "anagha", "arun", "arunprabhu", "arunprabuuuuuu",
    "arif", "durka", "mahalakshmi", "manjula", "sasikala", "vinothkumar",
    "sir", "mam", "maam", "msec", "ece", "dear", "students", "everyone",
    "thank", "thanks", "thankyou", "congrats", "congratulations", "super",
    "ok", "okay", "yes", "no", "pls", "please", "bro", "dude", "mam",
    "dont", "don", "afterwards", "yr", "year",
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
    "nov", "dec", "am", "pm", "lic",
}

COMMON_TOPIC_WORDS = {
    "and", "are", "for", "from", "has", "have", "her", "him", "his", "its",
    "more", "our", "the", "their", "them", "this", "that", "was", "were",
    "with", "you", "your", "they", "will", "should",
}

FILLER_PATTERNS = [
    r"^thank\s+you\s+(sir|mam|maam)?\.?$",
    r"^thanks\s+(sir|mam|maam)?\.?$",
    r"^super\s+my\s+dears?\.?$",
    r"^ok(ay)?\.?$",
    r"^do?n'?t ask me afterwards\.?$",
]


OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODELS = {
    "accurate": ["mistral:latest", "phi3:latest"],
    "fast": ["phi3:latest", "mistral:latest"],
}


def ollama_generate(prompt, max_tokens=200, mode="accurate"):
    models = OLLAMA_MODELS.get(mode, OLLAMA_MODELS["accurate"])

    for model in models:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": max_tokens,
                "top_p": 0.9,
            },
        }

        try:
            r = requests.post(OLLAMA_URL, json=payload, timeout=120)
            if not r.ok:
                continue

            response = r.json().get("response", "").strip()
            if response:
                return response
        except requests.RequestException:
            continue

    return ""


def clean_chat(chat):
    return chat.strip()


def select_last_messages(chat, last_n):
    lines = [line for line in chat.split("\n") if line.strip()]
    if last_n and last_n > 0:
        lines = lines[-last_n:]
    return "\n".join(lines)


def is_noise(text):
    text = text.lower()
    if "<media omitted>" in text:
        return True
    if len(text) < 4:
        return True
    if re.search(r"\.(jpg|png|mp4|webp|pdf)", text):
        return True
    return False


def parse_chat_line(line):
    line = line.strip()
    patterns = [
        r"^\[(?P<time>\d{1,2}:\d{2}),\s*(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\]\s*(?P<user>[^:]+):\s*(?P<text>.*)$",
        r"^(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),?\s*(?P<time>\d{1,2}:\d{2})(?:\s?[AP]M)?\s+-\s*(?P<user>[^:]+):\s*(?P<text>.*)$",
    ]

    for pattern in patterns:
        match = re.match(pattern, line)
        if match:
            return {
                "raw": line,
                "user": match.group("user").strip(),
                "text": match.group("text").strip(),
            }

    return {"raw": line, "user": "", "text": line}


def normalize_topic_text(text):
    text = text.lower()
    text = re.sub(r"<media omitted>", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\b\d{1,2}[:/.-]\d{1,2}(?:[:/.-]\d{2,4})?\b", " ", text)
    text = re.sub(r"\b\d+\b", " ", text)
    text = re.sub(r"[^a-z\s]", " ", text)
    words = [
        word for word in text.split()
        if len(word) > 2
        and word not in TOPIC_STOPWORDS
        and word not in COMMON_TOPIC_WORDS
    ]
    return " ".join(words)


def is_filler_message(text):
    normalized = normalize_topic_text(text)
    lowered = re.sub(r"[^a-z\s]", " ", text.lower()).strip()
    lowered = re.sub(r"\s+", " ", lowered)

    if not normalized:
        return True
    if len(normalized.split()) < 2:
        return True
    return any(re.match(pattern, lowered) for pattern in FILLER_PATTERNS)


def summary_instructions(mode):
    instructions = {
        "tldr": "Return a TLDR in exactly 2 short lines.",
        "bullets": "Return concise bullet points only.",
        "minutes": "Return meeting minutes with topics, decisions, and action items.",
        "normal": "Return a clear structured summary with main topics, decisions, and action items.",
    }
    return instructions.get(mode, instructions["normal"])


def simple_kmeans(vectors, k, iterations=8):
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / np.maximum(norms, 1e-9)
    centroids = vectors[:k].copy()
    labels = np.zeros(vectors.shape[0], dtype=int)

    for _ in range(iterations):
        distances = ((vectors[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        labels = distances.argmin(axis=1)

        for cluster_id in range(k):
            members = vectors[labels == cluster_id]
            if len(members) > 0:
                centroids[cluster_id] = members.mean(axis=0)

    return labels


def cosine_similarity_matrix(matrix):
    dense = matrix.toarray()
    norms = np.linalg.norm(dense, axis=1, keepdims=True)
    dense = dense / np.maximum(norms, 1e-9)
    return dense @ dense.T


def keyword_set(text):
    return {
        word for word in text.split()
        if word not in TOPIC_STOPWORDS and word not in COMMON_TOPIC_WORDS
    }


def group_related_messages(x_matrix, normalized_messages):
    similarity = cosine_similarity_matrix(x_matrix)
    keyword_sets = [keyword_set(text) for text in normalized_messages]
    visited = set()
    groups = []

    for start in range(len(normalized_messages)):
        if start in visited:
            continue

        stack = [start]
        visited.add(start)
        group = []

        while stack:
            current = stack.pop()
            group.append(current)

            for candidate in range(len(normalized_messages)):
                if candidate in visited:
                    continue

                overlap = len(keyword_sets[current] & keyword_sets[candidate])
                related = similarity[current, candidate] >= 0.22 or overlap >= 2
                if related:
                    visited.add(candidate)
                    stack.append(candidate)

        groups.append(group)

    return groups


def make_topic_summary(cluster_messages, mode):
    if len(cluster_messages) == 1:
        return cluster_messages[0]

    prompt = f"""
Summarize these related chat messages as one topic.
Rules:
- Use only the messages below.
- One short sentence.
- Do not add outside context.
- Do not mention timestamps unless needed.

MESSAGES:
{chr(10).join(cluster_messages[:8])}

TOPIC:
"""
    summary = ollama_generate(prompt, 60, mode)
    return summary or cluster_messages[0]


@app.get("/")
def root():
    return {"status": "Backend running"}


@app.post("/summarize")
def summarize(req: SummarizeRequest):
    chat = select_last_messages(clean_chat(req.chat_text), req.last_n)
    evidence_rule = (
        "Use only evidence from the chat. If something is unclear, say it is unclear."
        if req.evidence
        else "Summarize naturally, but do not invent facts."
    )

    prompt = f"""
{summary_instructions(req.mode)}
{evidence_rule}

CHAT:
{chat}
"""

    try:
        result = ollama_generate(prompt, 250, req.model)
        return {"summary": result}
    except Exception:
        return {"summary": "Error generating summary"}


@app.post("/ask")
def ask(req: AskRequest):
    chat = clean_chat(req.chat_text)

    prompt = f"""
Answer the question using ONLY the chat.
If unclear, say: Unclear from this chat.

CHAT:
{chat}

QUESTION:
{req.question}

ANSWER:
"""

    try:
        result = ollama_generate(prompt, 150, req.model)
        return {"answer": result}
    except Exception:
        return {"answer": "Error answering question"}


@app.post("/analytics")
def analytics(req: AnalyticsRequest):
    chat = select_last_messages(req.chat_text, req.last_n)
    messages = [m.strip() for m in chat.split("\n") if m.strip()]
    total = len(messages)

    word_count = {}
    messages_per_user = {}
    day_count = {}
    hour_count = {}

    for msg in messages:
        match = re.match(
            r"^(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}):(\d{2})(?:\s?[AP]M)?\s+-\s+([^:]+):",
            msg,
        )
        if match:
            day = match.group(1)
            hour = match.group(2)
            user = match.group(4).strip()
            day_count[day] = day_count.get(day, 0) + 1
            hour_count[hour] = hour_count.get(hour, 0) + 1
            messages_per_user[user] = messages_per_user.get(user, 0) + 1

        words = re.findall(r"[a-zA-Z']+", msg.lower())
        for word in words:
            if len(word) < 3:
                continue
            word_count[word] = word_count.get(word, 0) + 1

    top_words = [
        {"word": word, "count": count}
        for word, count in sorted(word_count.items(), key=lambda x: x[1], reverse=True)[:10]
    ]
    most_active_day = max(day_count.items(), key=lambda x: x[1])[0] if day_count else None
    most_active_hour = max(hour_count.items(), key=lambda x: x[1])[0] if hour_count else None

    return {
        "total_messages": total,
        "messages_per_user": messages_per_user,
        "most_active_day": most_active_day,
        "most_active_hour": most_active_hour,
        "top_words": top_words,
        "top_emojis": [],
    }


@app.post("/topics")
def topics(req: TopicsRequest):
    chat = select_last_messages(req.chat_text, req.last_n)
    parsed_messages = []

    for line in chat.split("\n"):
        if not line.strip() or is_noise(line):
            continue

        parsed = parse_chat_line(line)
        if is_filler_message(parsed["text"]) and parsed_messages and not parsed["user"] and not parsed_messages[-1]["user"]:
            parsed_messages[-1]["raw"] = f"{parsed_messages[-1]['raw']}\n{parsed['raw']}"
            parsed_messages[-1]["text"] = f"{parsed_messages[-1]['text']} {parsed['text']}"
            parsed_messages[-1]["normalized"] = normalize_topic_text(parsed_messages[-1]["text"])
            continue

        if is_filler_message(parsed["text"]):
            continue

        normalized = normalize_topic_text(f"{parsed['user']} {parsed['text']}")
        if not normalized:
            continue

        if parsed_messages and not parsed["user"] and not parsed_messages[-1]["user"]:
            parsed_messages[-1]["raw"] = f"{parsed_messages[-1]['raw']}\n{parsed['raw']}"
            parsed_messages[-1]["text"] = f"{parsed_messages[-1]['text']} {parsed['text']}"
            parsed_messages[-1]["normalized"] = normalize_topic_text(parsed_messages[-1]["text"])
        else:
            parsed_messages.append({
                "raw": parsed["raw"],
                "user": parsed["user"],
                "text": parsed["text"],
                "normalized": normalized,
            })

    if len(parsed_messages) < 2:
        return {"topics": []}

    normalized_messages = [message["normalized"] for message in parsed_messages]
    raw_messages = [message["raw"] for message in parsed_messages]
    topic_texts = [message["text"] for message in parsed_messages]

    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_df=0.85,
        min_df=1,
        ngram_range=(1, 2),
    )
    try:
        x_matrix = vectorizer.fit_transform(normalized_messages)
    except ValueError:
        return {"topics": []}

    words = vectorizer.get_feature_names_out()

    topics_result = []
    sample_count = max(1, req.sample_per_topic)
    groups = group_related_messages(x_matrix, normalized_messages)
    groups.sort(key=lambda group: (len(group), sum(len(raw_messages[i]) for i in group)), reverse=True)

    for group in groups:
        idx = np.array(group)
        cluster_msgs = [raw_messages[j] for j in idx]
        cluster_topic_texts = [topic_texts[j] for j in idx]
        normalized_cluster = " ".join(normalized_messages[j] for j in idx)

        if not cluster_msgs or len(normalized_cluster.split()) < 3:
            continue

        tfidf_sum = x_matrix[idx].sum(axis=0)
        scores = np.asarray(tfidf_sum).flatten()
        top_idx = scores.argsort()[::-1]
        keywords = []
        for word_index in top_idx:
            if scores[word_index] <= 0:
                break
            keyword = words[word_index]
            parts = keyword.split()
            if any(part in TOPIC_STOPWORDS for part in parts):
                continue
            if any(part.isdigit() for part in parts):
                continue
            keywords.append(keyword)
            if len(keywords) == 5:
                break

        if not keywords:
            continue

        summary = make_topic_summary(cluster_topic_texts, req.model)

        topics_result.append({
            "topic_id": len(topics_result),
            "chunk_id": 0,
            "keywords": keywords,
            "sample_messages": cluster_msgs[:sample_count],
            "topic_summary": summary,
        })

        if len(topics_result) >= req.max_topics:
            break

    return {"topics": topics_result}
