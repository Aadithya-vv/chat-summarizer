from fastapi import FastAPI, Request
from fastapi.responses import Response
from pydantic import BaseModel
import os
import json
import uuid
from datetime import datetime

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

import warnings
import requests
import re
from collections import Counter
import numpy as np

from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS

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


class MemoryImportRequest(BaseModel):
    chat_text: str
    name: str = "Untitled chat"


class SearchRequest(BaseModel):
    query: str
    chat_text: str = ""
    limit: int = 8


class NoiseRequest(BaseModel):
    chat_text: str
    limit: int = 30


class ExplainRequest(BaseModel):
    chat_text: str
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
MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory_store.json")
OLLAMA_MODELS = {
    "accurate": ["mistral:latest", "phi3:latest"],
    "fast": ["phi3:latest", "mistral:latest"],
}

IMPORTANT_WORDS = {
    "announce", "announcement", "assignment", "attendance", "bring", "class",
    "collect", "deadline", "due", "exam", "form", "hall", "important",
    "material", "meeting", "placement", "project", "remedial", "report",
    "submit", "test", "ticket", "tomorrow", "venue", "verify",
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


def read_memory_store():
    if not os.path.exists(MEMORY_FILE):
        return {"chats": []}

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {"chats": []}

    if "chats" not in data or not isinstance(data["chats"], list):
        return {"chats": []}
    return data


def write_memory_store(data):
    with open(MEMORY_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def select_last_messages(chat, last_n):
    lines = [line for line in chat.split("\n") if line.strip()]
    if last_n and last_n > 0:
        lines = lines[-last_n:]
    return "\n".join(lines)


def parse_chat_messages(chat):
    messages = []
    active = None

    for line in chat.split("\n"):
        if not line.strip():
            continue

        metadata = parse_chat_metadata(line)
        has_metadata = bool(metadata["date"] or metadata["user"])

        if has_metadata:
            if active:
                messages.append(active)
            active = {
                "date": metadata["date"],
                "time": metadata["time"],
                "user": metadata["user"] or "Unknown",
                "text": metadata["text"],
                "raw": line.strip(),
            }
            continue

        if active:
            active["text"] = f"{active['text']}\n{line.strip()}".strip()
            active["raw"] = f"{active['raw']}\n{line.strip()}".strip()
        else:
            active = {
                "date": "",
                "time": "",
                "user": "Unknown",
                "text": line.strip(),
                "raw": line.strip(),
            }

    if active:
        messages.append(active)

    return messages


def summarize_memory_stats(chats):
    total_messages = sum(chat.get("message_count", 0) for chat in chats)
    participants = set()
    dates = set()

    for chat in chats:
        participants.update(chat.get("participants", []))
        dates.update(chat.get("dates", []))

    return {
        "chat_count": len(chats),
        "total_messages": total_messages,
        "participants": sorted(participants),
        "date_count": len(dates),
    }


def search_messages(query, messages, limit):
    terms = [
        term for term in re.findall(r"[a-zA-Z0-9']+", query.lower())
        if len(term) > 1
    ]
    if not terms:
        return []

    matches = []
    for message in messages:
        haystack = f"{message.get('user', '')} {message.get('text', '')}".lower()
        score = sum(1 for term in terms if term in haystack)
        if score == 0:
            continue

        matches.append({
            "score": score,
            "chat_id": message.get("chat_id", ""),
            "chat_name": message.get("chat_name", ""),
            "date": message.get("date", ""),
            "user": message.get("user", ""),
            "text": message.get("text", ""),
            "raw": message.get("raw", ""),
        })

    matches.sort(key=lambda item: (item["score"], len(item["text"])), reverse=True)
    return matches[:max(1, limit)]


def message_importance_score(message):
    text = message.get("text", "")
    normalized = normalize_topic_text(text)
    words = set(normalized.split())
    score = len(words & IMPORTANT_WORDS)

    if re.search(r"\b(today|tomorrow|deadline|due|submit|bring|collect|exam|test)\b", text, re.I):
        score += 2
    if re.search(r"\b\d{1,2}[:/.-]\d{1,2}\b", text):
        score += 1
    if len(text) > 80:
        score += 1
    if is_filler_message(text):
        score -= 3

    return score


def important_messages_from_chat(chat, limit=30):
    messages = parse_chat_messages(chat)
    ranked = []

    for message in messages:
        if is_noise(message["text"]):
            continue

        score = message_importance_score(message)
        if score <= 0:
            continue

        ranked.append({
            "score": score,
            "date": message["date"],
            "user": message["user"],
            "text": message["text"],
            "raw": message["raw"],
        })

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:max(1, limit)]


def parse_chat_metadata(line):
    line = re.sub(r"[\u200e\u200f\ufeff]", "", line).strip()
    time = r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)"
    date = r"(?P<date>\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})"
    sender = r"(?P<user>[^:\n]+):\s*(?P<text>.*)$"
    patterns = [
        rf"^\[{time},\s*{date}\]\s*{sender}",
        rf"^\[{date},?\s+{time}\]\s*{sender}",
        rf"^{date},?\s+{time}\s+-\s*{sender}",
        rf"^\[{time}\]\s*{sender}",
    ]

    for pattern in patterns:
        match = re.match(pattern, line, re.I)
        if match:
            return {
                "date": (match.groupdict().get("date") or "").strip(),
                "time": match.group("time").strip(),
                "user": match.group("user").strip(),
                "text": match.group("text").strip(),
            }

    return {"date": "", "time": "", "user": "", "text": line}


def split_chat_sections(chat, max_lines=180):
    lines = [line for line in chat.split("\n") if line.strip()]
    sections = []
    current = []
    current_date = ""
    current_users = set()

    def push_current():
        if current:
            sections.append({
                "date": current_date or "Unknown date",
                "users": sorted(current_users),
                "text": "\n".join(current),
                "line_count": len(current),
            })

    for line in lines:
        metadata = parse_chat_metadata(line)
        line_date = metadata["date"]
        starts_new_date = current and line_date and current_date and line_date != current_date
        starts_new_chunk = current and len(current) >= max_lines

        if starts_new_date or starts_new_chunk:
            push_current()
            current = []
            current_users = set()
            current_date = ""

        if line_date and not current_date:
            current_date = line_date
        if metadata["user"]:
            current_users.add(metadata["user"])
        current.append(line)

    push_current()
    return sections


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
    metadata = parse_chat_metadata(line)
    return {"raw": line.strip(), "user": metadata["user"], "text": metadata["text"]}


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
        "tldr": "Return a friendly TLDR in exactly 2 short lines.",
        "bullets": "Return 5 to 8 clean bullet points. Keep each bullet complete, specific, and under 25 words.",
        "minutes": "Return readable meeting minutes with short sections for context, decisions, and action items.",
        "normal": (
            "Return a warm, easy-to-scan digest. Use short Markdown sections: "
            "At a glance, Key moments, Decisions or plans, and Things to remember."
        ),
    }
    return instructions.get(mode, instructions["normal"])


def summary_token_limit(mode):
    limits = {
        "tldr": 120,
        "bullets": 420,
        "minutes": 520,
        "normal": 380,
    }
    return limits.get(mode, limits["normal"])


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


def summarize_chat_section(section, index, total, model):
    users = ", ".join(section["users"]) if section["users"] else "Unknown participants"
    prompt = f"""
Summarize this chat section.
Rules:
- Use only this section.
- Do not ignore logistics, decisions, jokes, plans, or emotional tone.
- Preserve participant names when useful.
- Return 3 to 5 short bullets with natural wording.

SECTION {index} OF {total}
Date: {section["date"]}
Participants: {users}

CHAT:
{section["text"]}

SECTION SUMMARY:
"""
    return ollama_generate(prompt, 220, model)


def summarize_from_sections(sections, req, evidence_rule):
    section_summaries = []

    for index, section in enumerate(sections, start=1):
        users = ", ".join(section["users"]) if section["users"] else "Unknown participants"
        summary = summarize_chat_section(section, index, len(sections), req.model)
        if not summary:
            summary = "No reliable summary generated for this section."

        section_summaries.append(
            f"SECTION {index}\n"
            f"Date: {section['date']}\n"
            f"Participants: {users}\n"
            f"Messages: {section['line_count']}\n"
            f"{summary}"
        )

    combined = "\n\n".join(section_summaries)
    prompt = f"""
{summary_instructions(req.mode)}
{evidence_rule}

You are combining summaries from multiple parts of the same pasted chat.
Rules:
- Cover EVERY section below, including the earliest section.
- If sections have different dates or participants, keep those conversations distinct.
- Do not replace earlier conversations with later ones.
- Use only the section summaries below.
- Write for a normal person reading a chat recap, not an academic report.
- Prefer short paragraphs and crisp bullets over dense explanation.

SECTION SUMMARIES:
{combined}

FINAL SUMMARY:
"""
    return ollama_generate(prompt, summary_token_limit(req.mode), req.model)


@app.get("/")
def root():
    return {"status": "Backend running"}


@app.get("/memory")
def get_memory():
    store = read_memory_store()
    chats = store["chats"]
    return {
        "summary": summarize_memory_stats(chats),
        "chats": [
            {
                "id": chat["id"],
                "name": chat["name"],
                "created_at": chat["created_at"],
                "message_count": chat["message_count"],
                "participants": chat["participants"],
                "dates": chat["dates"],
            }
            for chat in chats
        ],
    }


@app.post("/memory/import")
def import_memory(req: MemoryImportRequest):
    chat = clean_chat(req.chat_text)
    messages = parse_chat_messages(chat)
    if not messages:
        return {"error": "No messages found."}

    participants = sorted({message["user"] for message in messages if message["user"] and message["user"] != "Unknown"})
    dates = sorted({message["date"] for message in messages if message["date"]})
    chat_id = str(uuid.uuid4())
    now = datetime.now().isoformat(timespec="seconds")

    store = read_memory_store()
    store["chats"].append({
        "id": chat_id,
        "name": req.name.strip() or "Untitled chat",
        "created_at": now,
        "message_count": len(messages),
        "participants": participants,
        "dates": dates,
        "messages": messages,
    })
    write_memory_store(store)

    return {
        "id": chat_id,
        "message_count": len(messages),
        "participants": participants,
        "dates": dates,
    }


@app.post("/memory/search")
def search_memory(req: SearchRequest):
    store = read_memory_store()
    memory_messages = []

    for chat in store["chats"]:
        for message in chat.get("messages", []):
            memory_messages.append({
                **message,
                "chat_id": chat["id"],
                "chat_name": chat["name"],
            })

    pasted_messages = [
        {**message, "chat_id": "current", "chat_name": "Current chat"}
        for message in parse_chat_messages(req.chat_text)
    ]
    matches = search_messages(req.query, pasted_messages + memory_messages, req.limit)
    return {"matches": matches}


@app.post("/noise")
def noise_killer(req: NoiseRequest):
    return {"important_messages": important_messages_from_chat(req.chat_text, req.limit)}


@app.post("/explain")
def explain_chat(req: ExplainRequest):
    chat = clean_chat(req.chat_text)
    important = important_messages_from_chat(chat, 12)
    important_text = "\n".join(item["raw"] for item in important) or chat[:3000]

    prompt = f"""
Explain what is happening in this chat for a busy student.
Rules:
- Use only the chat lines below.
- Be direct and practical.
- Separate announcements, confusing context, and what the reader should notice.
- If the chat is unclear, say what is unclear.

CHAT LINES:
{important_text}

EXPLANATION:
"""

    result = ollama_generate(prompt, 260, req.model)
    if not result:
        result = "I could not reach the local model. The important messages are listed in Noise Killer."

    return {
        "explanation": result,
        "evidence": important,
    }


@app.post("/summarize")
def summarize(req: SummarizeRequest):
    chat = select_last_messages(clean_chat(req.chat_text), req.last_n)
    sections = split_chat_sections(chat)
    evidence_rule = (
        "Use only evidence from the chat. If something is unclear, say it is unclear."
        if req.evidence
        else "Summarize naturally, but do not invent facts."
    )

    use_section_summaries = len(sections) > 1 or sum(section["line_count"] for section in sections) > 120

    if use_section_summaries:
        try:
            result = summarize_from_sections(sections, req, evidence_rule)
            return {"summary": result}
        except Exception:
            return {"summary": "Error generating summary"}

    prompt = f"""
{summary_instructions(req.mode)}
{evidence_rule}

CHAT:
{chat}
"""

    try:
        result = ollama_generate(prompt, summary_token_limit(req.mode), req.model)
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
    messages = parse_chat_messages(req.chat_text)
    if req.last_n > 0:
        messages = messages[-req.last_n:]
    total = len(messages)

    word_count = {}
    messages_per_user = {}
    day_count = {}
    hour_count = {}

    sender_words = {
        word for message in messages
        for word in re.findall(r"[a-zA-Z']+", message["user"].lower())
    }
    for msg in messages:
        day, user = msg["date"], msg["user"]
        if day:
            day_count[day] = day_count.get(day, 0) + 1
        if user != "Unknown":
            messages_per_user[user] = messages_per_user.get(user, 0) + 1
        time_match = re.fullmatch(r"(\d{1,2}):\d{2}(?::\d{2})?\s*([AP]M)?", msg["time"], re.I)
        if time_match:
            hour = int(time_match.group(1))
            period = (time_match.group(2) or "").upper()
            if period:
                hour = hour % 12 + (12 if period == "PM" else 0)
            hour_label = f"{hour:02d}:00"
            hour_count[hour_label] = hour_count.get(hour_label, 0) + 1

        words = re.findall(r"[a-zA-Z']+", msg["text"].lower())
        for word in words:
            if len(word) < 3 or word in ENGLISH_STOP_WORDS or word in sender_words:
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
    messages = parse_chat_messages(req.chat_text)
    # Plain pasted text has no message boundaries; treat each nonempty line as an entry.
    if messages and all(message["user"] == "Unknown" for message in messages):
        messages = [parse_chat_line(line) for line in req.chat_text.splitlines() if line.strip()]
    if req.last_n > 0:
        messages = messages[-req.last_n:]
    parsed_messages = []

    for parsed in messages:
        if is_noise(parsed["text"]) or is_filler_message(parsed["text"]):
            continue

        normalized = normalize_topic_text(parsed['text'])
        if not normalized:
            continue

        parsed_messages.append({**parsed, "normalized": normalized})

    if not parsed_messages:
        return {"topics": []}

    normalized_messages = [message["normalized"] for message in parsed_messages]
    raw_messages = [message["raw"] for message in parsed_messages]
    topic_texts = [message["text"] for message in parsed_messages]

    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_df=1.0,
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

        if not cluster_msgs or len(normalized_cluster.split()) < 2:
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
