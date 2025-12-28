import { useState } from "react";

function App() {
  const [chat, setChat] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);

  async function summarizeChat() {
    if (!chat.trim()) return;

    setLoading(true);
    setSummary("");

    try {
      const res = await fetch("http://127.0.0.1:8000/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_text: chat, mode: "tldr" })
      });

      const data = await res.json();
      setSummary(data.summary);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.canvas}>
      {/* LEFT */}
      <div style={styles.panel}>
        <div style={styles.header}>Chat Input</div>
        <textarea
          style={styles.textarea}
          placeholder="Paste your unread chat here..."
          value={chat}
          onChange={(e) => setChat(e.target.value)}
        />
        <div style={styles.footer}>
          <button style={styles.button} onClick={summarizeChat}>
            {loading ? "Summarizing…" : "Summarize"}
          </button>
        </div>
      </div>

      {/* RIGHT */}
      <div style={styles.panel}>
        <div style={styles.header}>Summary</div>
        <div style={styles.output}>
          {!summary && !loading && (
            <div style={styles.placeholder}>Summary will appear here</div>
          )}
          {loading && <div style={styles.placeholder}>Thinking…</div>}
          {summary && <pre style={styles.pre}>{summary}</pre>}
        </div>
      </div>
    </div>
  );
}

const styles = {
  canvas: {
    width: "100%",
    maxWidth: "1000px",     // 👈 CENTERED CHAT WIDTH
    height: "100vh",
    display: "flex",
    borderLeft: "1px solid #222",
    borderRight: "1px solid #222",
    backgroundColor: "#0f0f0f",
    color: "#eaeaea"
  },
  panel: {
    flex: 1,
    display: "flex",
    flexDirection: "column"
  },
  header: {
    padding: "14px 18px",
    fontSize: "13px",
    color: "#aaa",
    borderBottom: "1px solid #222"
  },
  textarea: {
    flex: 1,
    backgroundColor: "#0f0f0f",
    color: "#fff",
    border: "none",
    outline: "none",
    padding: "18px",
    fontSize: "14px",
    resize: "none",
    lineHeight: "1.6"
  },
  footer: {
    padding: "14px",
    borderTop: "1px solid #222",
    display: "flex",
    justifyContent: "flex-end"
  },
  button: {
    backgroundColor: "#1f1f1f",
    color: "#fff",
    border: "1px solid #333",
    padding: "8px 16px",
    cursor: "pointer"
  },
  output: {
    flex: 1,
    padding: "18px",
    overflowY: "auto"
  },
  placeholder: {
    color: "#666"
  },
  pre: {
    whiteSpace: "pre-wrap",
    fontSize: "14px",
    lineHeight: "1.6"
  }
};

export default App;
