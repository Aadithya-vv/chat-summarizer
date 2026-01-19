import { useMemo, useState } from "react";
import JSZip from "jszip";
import "./App.css";

function App() {
  const [chat, setChat] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);

  const [copied, setCopied] = useState(false);
  const [model, setModel] = useState("accurate"); // fast | accurate
  const [lastN, setLastN] = useState(0); // 0 = summarize all
  const [statusMsg, setStatusMsg] = useState("");

  // Ask feature
  const [question, setQuestion] = useState("");
  const [askLoading, setAskLoading] = useState(false);
  const [answer, setAnswer] = useState("");

  // Analytics feature
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analytics, setAnalytics] = useState(null);

  // ✅ NGROK BACKEND URL (so it works on phone also)
  const API_BASE = "https://ungovernable-noncohesively-maryln.ngrok-free.dev";

  const canSummarize = useMemo(() => chat.trim().length > 0 && !loading, [chat, loading]);

  const canAsk = useMemo(
    () => summary.trim().length > 0 && question.trim().length > 0 && !askLoading,
    [summary, question, askLoading]
  );

  const canAnalyze = useMemo(
    () => chat.trim().length > 0 && !analyticsLoading,
    [chat, analyticsLoading]
  );

  async function summarizeChat() {
    if (!chat.trim()) return;

    setLoading(true);
    setSummary("");
    setCopied(false);
    setStatusMsg("");
    setAnswer("");
    setQuestion("");

    try {
      const payload = {
        chat_text: chat,
        model: model,
        last_n: Number(lastN) || 0
      };

      const res = await fetch(`${API_BASE}/summarize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await res.json();

      if (!res.ok) {
        setSummary("");
        setStatusMsg(data?.detail || "Error generating summary.");
        return;
      }

      setSummary(data.summary || "");
    } catch (e) {
      console.error(e);
      setSummary("");
      setStatusMsg("Error generating summary.");
    } finally {
      setLoading(false);
    }
  }

  async function askMyChat() {
    if (!summary.trim() || !question.trim()) return;

    setAskLoading(true);
    setAnswer("");
    setStatusMsg("");

    try {
      const payload = {
        chat_text: chat,
        summary: summary,
        question: question,
        model: model
      };

      const res = await fetch(`${API_BASE}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await res.json();

      if (!res.ok) {
        setAnswer("");
        setStatusMsg(data?.detail || "Error answering question.");
        return;
      }

      setAnswer(data.answer || "");
    } catch (e) {
      console.error(e);
      setAnswer("");
      setStatusMsg("Error answering question.");
    } finally {
      setAskLoading(false);
    }
  }

  async function analyzeChat() {
    if (!chat.trim()) return;

    setAnalyticsLoading(true);
    setStatusMsg("");
    setAnalytics(null);

    try {
      const payload = {
        chat_text: chat,
        last_n: 0 // analyze full chat box by default
      };

      const res = await fetch(`${API_BASE}/analytics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await res.json();

      if (!res.ok) {
        setAnalytics(null);
        setStatusMsg(data?.detail || "Error generating analytics.");
        return;
      }

      setAnalytics(data);
    } catch (e) {
      console.error(e);
      setAnalytics(null);
      setStatusMsg("Error generating analytics.");
    } finally {
      setAnalyticsLoading(false);
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

  // ✅ ZIP Upload Handler
  async function handleZipUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    setStatusMsg("");
    setSummary("");
    setCopied(false);
    setAnswer("");
    setQuestion("");
    setAnalytics(null);

    try {
      setStatusMsg("📦 Reading ZIP...");

      const arrayBuffer = await file.arrayBuffer();
      const zip = await JSZip.loadAsync(arrayBuffer);

      // Find all .txt files
      const txtFiles = [];
      zip.forEach((relativePath, zipEntry) => {
        if (!zipEntry.dir && relativePath.toLowerCase().endsWith(".txt")) {
          txtFiles.push(zipEntry);
        }
      });

      if (txtFiles.length === 0) {
        setStatusMsg("❌ No .txt file found inside ZIP. Export chat again (Without media).");
        return;
      }

      // Pick the biggest .txt file (most likely the chat)
      let bestFile = null;
      let bestSize = -1;

      for (const entry of txtFiles) {
        const content = await entry.async("string");
        const size = content.length;
        if (size > bestSize) {
          bestSize = size;
          bestFile = { entry, content };
        }
      }

      if (!bestFile) {
        setStatusMsg("❌ Could not read chat text from ZIP.");
        return;
      }

      setChat(bestFile.content);
      setStatusMsg(`✅ Loaded: ${bestFile.entry.name}`);
    } catch (err) {
      console.error(err);
      setStatusMsg("❌ Failed to read ZIP. Try exporting again.");
    } finally {
      e.target.value = "";
    }
  }

  return (
    <div className="page">
      <div className="topbar">
        <div className="brand">
          <div className="logo">⚡</div>
          <div>
            <div className="title">Chat Summarizer</div>
            <div className="subtitle">Paste unread chats or upload WhatsApp ZIP</div>
          </div>
        </div>
      </div>

      <div className="container">
        {/* CHAT PANEL */}
        <section className="panel">
          <header className="panel-header">
            <div className="panel-title">Chat Input</div>

            <div className="controls">
              <label className="file-btn">
                Upload WhatsApp ZIP
                <input type="file" accept=".zip" onChange={handleZipUpload} />
              </label>

              <select
                className="select"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={loading || askLoading || analyticsLoading}
              >
                <option value="fast">⚡ Fast</option>
                <option value="accurate">🧠 Accurate</option>
              </select>

              <input
                className="input"
                type="number"
                min="0"
                placeholder="Last N (0 = all)"
                value={lastN}
                onChange={(e) => setLastN(e.target.value)}
                disabled={loading || askLoading || analyticsLoading}
              />
            </div>
          </header>

          <textarea
            className="textarea"
            value={chat}
            onChange={(e) => setChat(e.target.value)}
            placeholder="Paste unread chat messages here…"
            disabled={loading || askLoading || analyticsLoading}
          />

          <footer className="panel-footer">
            <button className="primary-btn" onClick={summarizeChat} disabled={!canSummarize}>
              {loading ? "Summarizing…" : "Summarize"}
            </button>

            <button className="secondary-btn" onClick={analyzeChat} disabled={!canAnalyze}>
              {analyticsLoading ? "Analyzing…" : "Analyze"}
            </button>

            <button
              className="secondary-btn"
              onClick={() => {
                setChat("");
                setSummary("");
                setStatusMsg("");
                setCopied(false);
                setQuestion("");
                setAnswer("");
                setAnalytics(null);
              }}
              disabled={loading || askLoading || analyticsLoading}
            >
              Clear
            </button>
          </footer>

          {statusMsg && <div className="status">{statusMsg}</div>}
        </section>

        {/* SUMMARY + ASK + ANALYTICS PANEL */}
        <section className="panel">
          <header className="panel-header">
            <div className="panel-title">Summary</div>

            <div className="actions">
              <button className="small-btn" onClick={copySummary} disabled={!summary}>
                {copied ? "Copied ✓" : "Copy"}
              </button>
              <button className="small-btn" onClick={downloadSummary} disabled={!summary}>
                Download
              </button>
            </div>
          </header>

          <div className="output">
            {!summary && !loading && <div className="placeholder">Your summary will appear here.</div>}
            {loading && <div className="placeholder">Thinking…</div>}
            {summary && <pre className="raw-output">{summary}</pre>}
          </div>

          {/* ASK MY CHAT */}
          <div style={{ marginTop: "12px" }}>
            <div style={{ fontWeight: 700, fontSize: "13px", marginBottom: "8px", opacity: 0.9 }}>
              Ask My Chat
            </div>

            <input
              className="textarea"
              style={{ height: "44px" }}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder='Example: "Why did he say uninstall it?"'
              disabled={!summary || loading || askLoading || analyticsLoading}
            />

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "10px" }}>
              <button className="primary-btn" onClick={askMyChat} disabled={!canAsk}>
                {askLoading ? "Answering…" : "Ask"}
              </button>
            </div>

            <div className="output" style={{ marginTop: "10px", minHeight: "120px" }}>
              {!answer && !askLoading && <div className="placeholder">Answer will appear here.</div>}
              {askLoading && <div className="placeholder">Thinking…</div>}
              {answer && <pre className="raw-output">{answer}</pre>}
            </div>
          </div>

          {/* ANALYTICS */}
          <div style={{ marginTop: "12px" }}>
            <div style={{ fontWeight: 700, fontSize: "13px", marginBottom: "8px", opacity: 0.9 }}>
              Analytics
            </div>

            {!analytics && !analyticsLoading && (
              <div className="placeholder">Click "Analyze" to see chat statistics.</div>
            )}

            {analyticsLoading && <div className="placeholder">Crunching numbers…</div>}

            {analytics && (
              <div className="output" style={{ marginTop: "10px", minHeight: "180px" }}>
                <div style={{ fontSize: "13px", lineHeight: "1.6" }}>
                  <div><b>Total Messages:</b> {analytics.total_messages}</div>
                  <div><b>Most Active Day:</b> {analytics.most_active_day || "N/A"}</div>
                  <div><b>Most Active Hour:</b> {analytics.most_active_hour || "N/A"}</div>

                  <div style={{ marginTop: "12px" }}>
                    <b>Messages per User:</b>
                    <ul style={{ margin: "6px 0 0 18px" }}>
                      {Object.entries(analytics.messages_per_user || {}).map(([user, count]) => (
                        <li key={user}>{user}: {count}</li>
                      ))}
                    </ul>
                  </div>

                  <div style={{ marginTop: "12px" }}>
                    <b>Top 20 Words:</b>
                    <div style={{ marginTop: "6px", display: "flex", flexWrap: "wrap", gap: "6px" }}>
                      {(analytics.top_words || []).map((w) => (
                        <span
                          key={w.word}
                          style={{
                            padding: "6px 10px",
                            borderRadius: "999px",
                            background: "rgba(255,255,255,0.06)",
                            border: "1px solid rgba(255,255,255,0.10)",
                            fontSize: "12px"
                          }}
                        >
                          {w.word} ({w.count})
                        </span>
                      ))}
                    </div>
                  </div>

                  <div style={{ marginTop: "12px" }}>
                    <b>Top Emojis:</b>
                    <div style={{ marginTop: "6px", display: "flex", flexWrap: "wrap", gap: "10px" }}>
                      {(analytics.top_emojis || []).map((e) => (
                        <span
                          key={e.emoji}
                          style={{
                            padding: "6px 10px",
                            borderRadius: "12px",
                            background: "rgba(255,255,255,0.06)",
                            border: "1px solid rgba(255,255,255,0.10)",
                            fontSize: "14px"
                          }}
                        >
                          {e.emoji} <span style={{ opacity: 0.7, fontSize: "12px" }}>({e.count})</span>
                        </span>
                      ))}
                    </div>
                  </div>

                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

export default App;
