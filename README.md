# Chat Summarizer

A local-first AI workspace for messy WhatsApp and group chats.

The app lets you paste a chat or upload a WhatsApp ZIP export, then summarize it, ask questions, find important messages, search saved chats, and detect topics without sending chat data to a cloud API.

## Current Features

- Paste long chat conversations.
- Upload WhatsApp ZIP exports without media.
- Summarize chats with a local Ollama model.
- Ask questions using only the chat text.
- Analyze participant/message activity.
- Detect cleaner topics while ignoring filler such as thank-you messages.
- Save chats into local private memory.
- Search current and saved chats.
- Show only important messages with Noise Killer.
- Explain confusing chat context for busy students.
- Export summaries as text, Markdown, JSON, or action-only text.

## Tech Stack

- Frontend: React, Vite, JSZip, CSS
- Backend: FastAPI, Requests, NumPy, scikit-learn
- Local AI: Ollama with `mistral:latest` and/or `phi3:latest`

## Run Locally

Start Ollama:

```powershell
ollama serve
ollama pull mistral
ollama pull phi3
```

Start the backend:

```powershell
cd D:\chat-summarizer\backend
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Start the frontend:

```powershell
cd D:\chat-summarizer\frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173/
```

## Privacy

Saved chat memory is written locally to `backend/memory_store.json`. That file is ignored by Git.
