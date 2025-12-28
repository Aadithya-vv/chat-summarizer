# Chat Summarizer 🧠💬

A web application that summarizes long chat conversations (100+ unread messages) into clear, structured insights using a **local Large Language Model (LLM)**.

---

## 🚀 Features

- Paste long chat conversations (WhatsApp / Discord / Slack style)
- AI-generated structured summary:
  - 🧠 Main Topics
  - ✅ Decisions
  - 🛠 Action Items
- Optimized for large chats using chunking
- Runs **fully locally** (no paid APIs)
- ChatGPT-style dark UI
- Export summary:
  - 📋 Copy to clipboard
  - 📄 Download as `.txt`

---

## 🧠 How It Works (High Level)

1. User pastes a long chat conversation
2. Backend preprocesses and cleans the text
3. Chat is summarized using a **local LLM (Mistral via Ollama)**
4. Output is structured into topics, decisions, and actions
5. Frontend renders a clean, readable summary

---

## 🏗️ Architecture

Frontend (React)
|
| POST /summarize
|
Backend (FastAPI)
|
| Prompt + Chunking
|
Local LLM (Ollama - Mistral 7B)


---

## 🛠️ Tech Stack

### Frontend
- React (Vite)
- Plain CSS / Inline styles
- Fetch API

### Backend
- Python
- FastAPI
- Requests

### AI / ML
- Ollama
- Mistral 7B (local inference)

---

## ⚡ Performance Optimizations

- Chunking for very large chats
- Fast-path summarization for smaller chats
- Token limits and low-temperature decoding
- Reduced LLM calls for lower latency

Typical summary time (local):
- 100–150 messages → ~10–15 seconds

---

## ▶️ Running the Project Locally

### 1️⃣ Start the local LLM
```bash
ollama pull mistral
ollama serve
