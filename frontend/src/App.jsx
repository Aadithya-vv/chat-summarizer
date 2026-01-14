import { useState } from "react";
import "./App.css";

function App() {
  const [chat, setChat] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const [model, setModel] = useState("accurate"); // fast | accurate

  // user can type last N
  const [lastN, setLastN] = useState(100);

  // ✅ NEW: summarize mode
  // "all" => summarize everything pasted
  // "lastn" => summarize last N messages/lines
  const [summarizeMode, setSummarizeMode] = useState("lastn");

  // safety limits
  const MIN_N = 10;
  const MAX_N = 500;

  async function summarizeChat() {
    if (!chat.trim()) return;

    setLoading(true);
    setSummary("");
    setCopied(false);

    try {
      // ⚠️ change to ngrok when needed
      const BACKEND_URL = "http://127.0.0.1:8000/summarize";

      let safeN = Number(lastN);
      if (isNaN(safeN)) safeN = 100;
      if (safeN < MIN_N) safeN = MIN_N;
      if (safeN > MAX_N) safeN = MAX_N;

      // ✅ if summarizeMode=all, we send last_n = 0
      // backend interprets 0 as "do not trim"
      const finalLastN = summarizeMode === "all" ? 0 : safeN;

      const res = await fetch(BACKEND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_text: chat,
          model: model,
          last_n: finalLastN
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

  function copySummary() {
    if (!summary) return;
    navigator.clipboard.writeText(summary);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  function downloadSummary() {
    if (!summary) return;
    const blob = new Blob([summary], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "chat-summary.txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  function clearAll() {
    setChat("");
    setSummary("");
    setCopied(false);
  }

  return (
    <div className="page">
      <div className="container">
        {/* CHAT PANEL */}
        <section className="panel">
          <header className="panel-header row">
            <span>Chat Input</span>

            <div className="header-controls">
              {/* MODEL SELECT */}
              <select value={model} onChange={(e) => setModel(e.target.value)}>
                <option value="fast">⚡ Fast</option>
                <option value="accurate">🧠 Accurate</option>
              </select>
            </div>
          </header>

          {/* ✅ NEW: Summarize Mode Switch */}
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

            {/* show lastN input only in recent mode */}
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

          <p className="hint">
            {summarizeMode === "all"
              ? "🖥️ PC tip: If you pasted only unread messages, use All Pasted."
              : "📱 Mobile tip: If you exported a huge chat, Recent mode summarizes only the latest messages (like unread)."}
          </p>

          <textarea
            className="textarea"
            value={chat}
            onChange={(e) => setChat(e.target.value)}
            placeholder="Paste chat messages here…"
            disabled={loading}
          />

          <footer className="panel-footer">
            <button className="secondary-btn" onClick={clearAll} disabled={loading && !chat}>
              Clear
            </button>

            <button className="primary-btn" onClick={summarizeChat} disabled={loading}>
              {loading ? "Summarizing…" : "Summarize"}
            </button>
          </footer>
        </section>

        {/* SUMMARY PANEL */}
        <section className="panel">
          <header className="panel-header row">
            <span>Summary</span>
            <div className="actions">
              <button onClick={copySummary} disabled={!summary}>
                {copied ? "Copied ✓" : "Copy"}
              </button>
              <button onClick={downloadSummary} disabled={!summary}>
                Download
              </button>
            </div>
          </header>

          <div className="output">
            {!summary && !loading && (
              <div className="placeholder">Summary will appear here</div>
            )}
            {loading && <div className="placeholder">Thinking…</div>}
            {summary && <SafeSummaryRenderer text={summary} />}
          </div>
        </section>
      </div>
    </div>
  );
}

/* ---------- SAFE RENDERERS ---------- */

function SafeSummaryRenderer({ text }) {
  const structured =
    text.includes("🧠") || text.includes("✅") || text.includes("🛠") || text.includes("📌");

  if (!structured) {
    return <pre className="raw-output">{text}</pre>;
  }

  return <FormattedSummary text={text} />;
}

function FormattedSummary({ text }) {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);

  const data = {
    "Main Topics": [],
    "Decisions": [],
    "Action Items": [],
    "Notes / Context": []
  };

  let current = null;

  for (const line of lines) {
    if (line.startsWith("🧠")) current = "Main Topics";
    else if (line.startsWith("✅")) current = "Decisions";
    else if (line.startsWith("🛠")) current = "Action Items";
    else if (line.startsWith("📌")) current = "Notes / Context";
    else if (line.startsWith("-") && current) {
      data[current].push(line.replace(/^-\s*/, ""));
    }
  }

  return (
    <div>
      {Object.entries(data).map(([title, items]) => (
        <div key={title} className="section">
          <div className="section-title">{title}</div>
          {items.length === 0 ? (
            <div className="bullet">• None</div>
          ) : (
            items.map((item, i) => (
              <div key={i} className="bullet">• {item}</div>
            ))
          )}
        </div>
      ))}
    </div>
  );
}

export default App;
