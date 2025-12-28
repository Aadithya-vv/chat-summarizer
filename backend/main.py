from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from preprocess import clean_chat
from summarizer import summarize_chat

app = FastAPI()

# ✅ CORS FIX (THIS SOLVES OPTIONS ERROR)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # allow frontend
    allow_credentials=True,
    allow_methods=["*"],   # allow POST, OPTIONS, etc
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    chat_text: str
    mode: str

@app.post("/summarize")
def summarize(req: ChatRequest):
    cleaned = clean_chat(req.chat_text)
    summary = summarize_chat(cleaned, req.mode)
    return {"summary": summary}
