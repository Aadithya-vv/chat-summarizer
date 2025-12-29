import { useState } from "react";
import "./App.css";

function App() {
  const [chat, setChat] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [model, setModel] = useState("accurate"); // fast | accurate

  async function summarizeChat() {
    if (!chat.trim()) return;

    setLoading(true);
    setSummary("");
    setCopied(false);

    try {
      const res = await fetch("https://ungovernable-noncohesively-maryln.ngrok-free.dev/docs#/default/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_text: chat,
          model: model
        })
      });

      const data = await res.json();
      setSummary(data.summary || "");
    } catch (e) {
      console.error(e);
      setSummary("Error generating summary.");
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

  return (
    <div className="page">
      <div className="container">
        {/* CHAT PANEL */}
        <section className="panel">
          <header className="panel-header row">
            <span>Chat Input</span>

            {/* MODEL SELECT */}
            <select
              value={model}
              onChange={e => setModel(e.target.value)}
              style={{
                background: "#1f1f1f",
                color: "#ddd",
                border: "1px solid #333",
                padding: "4px 8px"
              }}
            >
              <option value="fast">⚡ Fast</option>
              <option value="accurate">🧠 Accurate</option>
            </select>
          </header>

          <textarea
            className="textarea"
            value={chat}
            onChange={e => setChat(e.target.value)}
            placeholder="Paste chat here…"
            disabled={loading}
          />

          <footer className="panel-footer">
            <button
              className="primary-btn"
              onClick={summarizeChat}
              disabled={loading}
            >
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
    text.includes("🧠") || text.includes("✅") || text.includes("🛠");

  if (!structured) {
    return <pre className="raw-output">{text}</pre>;
  }

  return <FormattedSummary text={text} />;
}

function FormattedSummary({ text }) {
  const lines = text.split("\n").map(l => l.trim()).filter(Boolean);

  const data = {
    "Main Topics": [],
    "Decisions": [],
    "Action Items": []
  };

  let current = null;

  for (const line of lines) {
    if (line.startsWith("🧠")) current = "Main Topics";
    else if (line.startsWith("✅")) current = "Decisions";
    else if (line.startsWith("🛠")) current = "Action Items";
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
