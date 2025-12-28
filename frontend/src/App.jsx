import { useState } from "react";
import "./App.css";

function App() {
  const [chat, setChat] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  async function summarizeChat() {
    if (!chat.trim()) return;

    setLoading(true);
    setSummary("");
    setCopied(false);

    try {
      const res = await fetch("http://127.0.0.1:8000/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_text: chat,
          mode: "tldr"
        })
      });

      const data = await res.json();
      setSummary(data.summary || data.result || "");
    } catch (err) {
      console.error(err);
      setSummary("Error: Could not generate summary.");
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
          <header className="panel-header">Chat Input</header>

          <textarea
            className="textarea"
            placeholder="Paste your unread chat messages here…"
            value={chat}
            onChange={(e) => setChat(e.target.value)}
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

            {summary && <SmartSummaryRenderer text={summary} />}
          </div>
        </section>
      </div>
    </div>
  );
}

/* ===== SMART RENDERER ===== */

function SmartSummaryRenderer({ text }) {
  const hasStructuredSections =
    text.includes("🧠") ||
    text.includes("✅") ||
    text.includes("🛠");

  if (hasStructuredSections) {
    return <FormattedSummary text={text} />;
  }

  // Fallback: render raw text cleanly
  return <pre className="raw-output">{text}</pre>;
}

/* ===== FORMATTED SUMMARY ===== */

function FormattedSummary({ text }) {
  const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
  let section = "";
  const data = {};

  lines.forEach(line => {
    if (line.startsWith("🧠")) {
      section = "Main Topics";
      data[section] = [];
    } else if (line.startsWith("✅")) {
      section = "Decisions";
      data[section] = [];
    } else if (line.startsWith("🛠")) {
      section = "Action Items";
      data[section] = [];
    } else if (line.startsWith("-") || line.startsWith("•")) {
      if (section) data[section].push(line.replace(/^[-•]\s*/, ""));
    }
  });

  return (
    <div>
      {Object.entries(data).map(([title, items]) => (
        <div key={title} className="section">
          <div className="section-title">{title}</div>
          {items.map((item, i) => (
            <div key={i} className="bullet">• {item}</div>
          ))}
        </div>
      ))}
    </div>
  );
}

export default App;
