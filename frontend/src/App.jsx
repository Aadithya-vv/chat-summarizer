import { useState } from "react";
import "./App.css";

function App() {
  const [chat, setChat] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);

  const [model, setModel] = useState("accurate");

  const [lastN, setLastN] = useState(100);
  const [summarizeMode, setSummarizeMode] = useState("lastn");

  // Ask My Chat
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);

  const MIN_N = 10;
  const MAX_N = 500;

  const BACKEND_BASE = "http://127.0.0.1:8000"; // change to ngrok when needed

  function getFinalLastN() {
    let safeN = Number(lastN);
    if (isNaN(safeN)) safeN = 100;
    if (safeN < MIN_N) safeN = MIN_N;
    if (safeN > MAX_N) safeN = MAX_N;
    return summarizeMode === "all" ? 0 : safeN;
  }

  async function summarizeChat() {
    if (!chat.trim()) return;

    setLoading(true);
    setSummary("");
    setAnswer("");
    setQuestion("");

    try {
      const res = await fetch(`${BACKEND_BASE}/summarize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_text: chat,
          model: model,
          last_n: getFinalLastN()
        })
      });

      if (!res.ok) throw new Error(`HTTP error: ${res.status}`);
      const data = await res.json();
      setSummary(data.summary || "");
    } catch (e) {
      console.error(e);
      setSummary("❌ Error generating summary.");
    } finally {
      setLoading(false);
    }
  }

  async function askMyChat() {
    if (!chat.trim()) {
      setAnswer("Please paste chat first.");
      return;
    }
    if (!question.trim()) return;

    setAsking(true);
    setAnswer("");

    try {
      const res = await fetch(`${BACKEND_BASE}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_text: chat,
          question: question,
          model: model,
          last_n: getFinalLastN()
        })
      });

      if (!res.ok) throw new Error(`HTTP error: ${res.status}`);
      const data = await res.json();
      setAnswer(data.answer || "");
    } catch (e) {
      console.error(e);
      setAnswer("❌ Error: Could not answer question.");
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="page">
      <div className="container">
        {/* CHAT PANEL */}
        <section className="panel">
          <header className="panel-header row">
            <span>Chat Input</span>

            <div className="header-controls">
              <select value={model} onChange={(e) => setModel(e.target.value)}>
                <option value="fast">⚡ Fast</option>
                <option value="accurate">🧠 Accurate</option>
              </select>
            </div>
          </header>

          <div className="mode-row">
            <div className="mode-tabs">
              <button
                className={summarizeMode === "lastn" ? "tab active" : "tab"}
                onClick={() => setSummarizeMode("lastn")}
                type="button"
              >
                Recent
              </button>

              <button
                className={summarizeMode === "all" ? "tab active" : "tab"}
                onClick={() => setSummarizeMode("all")}
                type="button"
              >
                All Pasted
              </button>
            </div>

            {summarizeMode === "lastn" && (
              <div className="lastn-wrap">
                <span className="lastn-label">Last</span>
                <input
                  className="lastn-input"
                  type="number"
                  value={lastN}
                  min={MIN_N}
                  max={MAX_N}
                  onChange={(e) => setLastN(e.target.value)}
                />
                <span className="lastn-label">msgs</span>
              </div>
            )}
          </div>

          <textarea
            className="textarea"
            value={chat}
            onChange={(e) => setChat(e.target.value)}
            placeholder="Paste chat messages here…"
            disabled={loading || asking}
          />

          <footer className="panel-footer">
            <button className="primary-btn" onClick={summarizeChat} disabled={loading || asking}>
              {loading ? "Summarizing…" : "Summarize"}
            </button>
          </footer>
        </section>

        {/* OUTPUT PANEL */}
        <section className="panel">
          <header className="panel-header row">
            <span>Summary</span>
          </header>

          <div className="output">
            {!summary && !loading && <div className="placeholder">Summary will appear here</div>}
            {loading && <div className="placeholder">Thinking…</div>}
            {summary && <pre className="raw-output">{summary}</pre>}
          </div>

          {/* ASK MY CHAT */}
          <div className="ask-box">
            <div className="ask-title">💬 Ask My Chat</div>

            <input
              className="ask-input"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder='Ask something like: "What was decided?"'
              disabled={asking || loading}
            />

            <button className="ask-btn" onClick={askMyChat} disabled={asking || loading}>
              {asking ? "Asking…" : "Ask"}
            </button>

            {answer && (
              <div className="ask-answer">
                <div className="ask-answer-title">Answer</div>
                <div className="ask-answer-text">{answer}</div>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

export default App;
