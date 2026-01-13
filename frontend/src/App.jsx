import { useState } from "react";
import "./App.css";

function App() {
  const [chat, setChat] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const [model, setModel] = useState("accurate"); // fast | accurate
  const [lastN, setLastN] = useState(100); // 50 | 100 | 300

  async function summarizeChat() {
    if (!chat.trim()) return;

    setLoading(true);
    setSummary("");
    setCopied(false);

    try {
      // ⚠️ IMPORTANT:
      // Replace this with your real backend URL (ngrok / render / railway)
      const BACKEND_URL = " https://ungovernable-noncohesively-maryln.ngrok-free.dev/summarize";

      const res = await fetch(BACKEND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_text: chat,
          model: model,
          last_n: lastN
        })
      });

      if (!res.ok) {
        throw new Error(`HTTP error: ${res.status}`);
      }

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
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
              >
                <option value="fast">⚡ Fast</option>
                <option value="accurate">🧠 Accurate</option>
              </select>

              {/* LAST N SELECT */}
              <select
                value={lastN}
                onChange={(e) => setLastN(Number(e.target.value))}
              >
                <option value={50}>Last 50 msgs</option>
                <option value={100}>Last 100 msgs</option>
                <option value={300}>Last 300 msgs</option>
              </select>
            </div>
          </header>

          <p className="hint">
            📱 Mobile tip: If you export a huge chat, this app summarizes only the most recent messages (like unread).
          </p>

          <textarea
            className="textarea"
            value={chat}
            onChange={(e) => setChat(e.target.value)}
            placeholder="Paste unread / recent chat messages here…"
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
