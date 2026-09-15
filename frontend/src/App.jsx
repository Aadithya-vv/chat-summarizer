import { useEffect, useMemo, useRef, useState } from "react";
import JSZip from "jszip";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";

const TABS = [
  { id: "summary", label: "Summary" },
  { id: "ask", label: "Ask" },
  { id: "analytics", label: "Analytics" },
  { id: "topics", label: "Topics" },
  { id: "memory", label: "Memory" },
  { id: "search", label: "Search" },
  { id: "noise", label: "Noise" },
  { id: "explain", label: "Explain" }
];

function parseChatStats(chat) {
  const lines = chat.split("\n").map((line) => line.trim()).filter(Boolean);
  const users = new Set();
  let lastMessage = "";
  let messageCount = 0;
  const time = String.raw`(?<time>\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)`;
  const date = String.raw`(?<date>\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})`;
  const sender = String.raw`(?<user>[^:\n]+):\s*`;
  const patterns = [
    new RegExp(String.raw`^\[${time},\s*${date}\]\s*${sender}`, "i"),
    new RegExp(String.raw`^\[${date},?\s+${time}\]\s*${sender}`, "i"),
    new RegExp(String.raw`^${date},?\s+${time}\s+-\s*${sender}`, "i"),
    new RegExp(String.raw`^\[${time}\]\s*${sender}`, "i")
  ];

  lines.forEach((line) => {
    const normalized = line.replace(/[\u200e\u200f\ufeff]/g, "").trim();
    const match = patterns.map((pattern) => normalized.match(pattern)).find(Boolean);
    if (match) {
      messageCount += 1;
      lastMessage = [match.groups.date, match.groups.time].filter(Boolean).join(" ");
      users.add(match.groups.user.trim());
    } else if (!messageCount) {
      messageCount = 1;
    }
  });

  return {
    messages: messageCount,
    participants: users.size,
    lastMessage: lastMessage || "Unknown",
    estimate: lines.length ? Math.max(1, Math.ceil(lines.length / 180)) : 0
  };
}

function normalizeTopWord(item) {
  if (Array.isArray(item)) {
    return { word: item[0], count: item[1] };
  }
  return item;
}

function extractActionItems(text) {
  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
  const start = lines.findIndex((line) => /action|todo|next step/i.test(line));
  if (start === -1) return text;

  const items = [];
  for (let i = start + 1; i < lines.length; i += 1) {
    const line = lines[i];
    if (/^[A-Z][A-Za-z ]+:$/.test(line) && items.length) break;
    if (/^[-*•]|\d+\./.test(line)) items.push(line.replace(/^[-*•]\s*/, ""));
  }
  return items.length ? items.join("\n") : text;
}

function formatBytes(bytes) {
  if (!bytes) return "0 KB";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function StructuredText({ text }) {
  if (!text) return null;

  const lines = text.split("\n");
  const blocks = [];
  let list = [];

  function flushList() {
    if (list.length) {
      blocks.push({ type: "list", items: list });
      list = [];
    }
  }

  lines.forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      return;
    }

    const bullet = line.match(/^[-*•]\s+(.+)/);
    const numbered = line.match(/^\d+\.\s+(.+)/);
    if (bullet || numbered) {
      list.push((bullet || numbered)[1]);
      return;
    }

    flushList();
    if (/^#{1,3}\s+/.test(line)) {
      blocks.push({ type: "heading", text: line.replace(/^#{1,3}\s+/, "") });
    } else if (/^[A-Z][A-Za-z /&-]{2,}:$/.test(line) || /^(Main Topics|Decisions|Action Items|Evidence|TLDR|Summary)/i.test(line)) {
      blocks.push({ type: "heading", text: line.replace(/:$/, "") });
    } else {
      blocks.push({ type: "paragraph", text: line });
    }
  });
  flushList();

  return (
    <div className="structured-output">
      {blocks.map((block, index) => {
        if (block.type === "heading") return <h3 key={index}>{block.text}</h3>;
        if (block.type === "list") {
          return (
            <ul key={index}>
              {block.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}
            </ul>
          );
        }
        return <p key={index}>{block.text}</p>;
      })}
    </div>
  );
}

function DigestText({ text }) {
  if (!text) return null;

  function cleanInline(value) {
    return value
      .replace(/\*\*(.*?)\*\*/g, "$1")
      .replace(/__(.*?)__/g, "$1")
      .replace(/^SECTION\s+\d+\s*[:.-]?\s*/i, "Conversation ")
      .trim();
  }

  const blocks = [];
  let list = [];

  function flushList() {
    if (list.length) {
      blocks.push({ type: "list", items: list });
      list = [];
    }
  }

  text.split("\n").forEach((rawLine) => {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      return;
    }

    const bullet = line.match(/^[-*\u2022]\s+(.+)/);
    const numbered = line.match(/^\d+\.\s+(.+)/);
    if (bullet || numbered) {
      list.push(cleanInline((bullet || numbered)[1]));
      return;
    }

    flushList();
    if (/^#{1,3}\s+/.test(line) || /^\*\*.+\*\*$/.test(line)) {
      blocks.push({ type: "heading", text: cleanInline(line.replace(/^#{1,3}\s+/, "")) });
    } else if (/^[A-Z][A-Za-z /&-]{2,}:$/.test(line) || /^(At a glance|Key moments|Decisions|Plans|Action Items|Things to remember|Evidence|TLDR|Summary|Main Topics)/i.test(line)) {
      blocks.push({ type: "heading", text: cleanInline(line.replace(/:$/, "")) });
    } else if (/^(Date|Participants|Messages):/i.test(line)) {
      blocks.push({ type: "meta", text: cleanInline(line) });
    } else {
      blocks.push({ type: "paragraph", text: cleanInline(line) });
    }
  });
  flushList();

  const intro = [];
  const cards = [];
  let currentCard = null;

  blocks.forEach((block) => {
    if (block.type === "heading") {
      currentCard = { title: block.text, blocks: [] };
      cards.push(currentCard);
      return;
    }

    if (currentCard) {
      currentCard.blocks.push(block);
    } else {
      intro.push(block);
    }
  });

  function renderBlock(block, index) {
    if (block.type === "list") {
      return (
        <ul key={index}>
          {block.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}
        </ul>
      );
    }
    if (block.type === "meta") return <div className="digest-meta" key={index}>{block.text}</div>;
    return <p key={index}>{block.text}</p>;
  }

  function cardPreview(card) {
    const firstParagraph = card.blocks.find((block) => block.type === "paragraph")?.text;
    const firstListItem = card.blocks.find((block) => block.type === "list")?.items?.[0];
    return firstParagraph || firstListItem || "Tap to read this part.";
  }

  function cardDate(card) {
    const metaDate = card.blocks
      .find((block) => block.type === "meta" && /^Date:/i.test(block.text))
      ?.text.replace(/^Date:\s*/i, "");
    const titleDate = card.title.match(/Date:\s*([^)]+)/i)?.[1];
    return metaDate || titleDate || "Summary";
  }

  const dateGroups = [];
  cards.forEach((card) => {
    const date = cardDate(card);
    const existingGroup = dateGroups.find((group) => group.date === date);

    if (existingGroup) {
      existingGroup.cards.push(card);
    } else {
      dateGroups.push({ date, cards: [card] });
    }
  });

  function groupPreview(group) {
    return group.cards.map((card) => card.title).slice(0, 2).join(" | ") || "Tap to read this date.";
  }

  return (
    <div className="structured-output digest-output">
      {intro.length > 0 && (
        <section className="digest-card digest-card-feature">
          {intro.map(renderBlock)}
        </section>
      )}

      {dateGroups.map((group, groupIndex) => (
        <details className="date-card" key={`${group.date}-${groupIndex}`} open={groupIndex === 0}>
          <summary>
            <span>
              <strong>{group.date}</strong>
              <small>{group.cards.length} section{group.cards.length === 1 ? "" : "s"} | {groupPreview(group)}</small>
            </span>
          </summary>
          <div className="date-card-body">
            {group.cards.map((card, index) => (
              <details className="digest-card digest-accordion" key={`${card.title}-${index}`} open={groupIndex === 0 && index === 0}>
                <summary>
                  <span>
                    <strong>{card.title}</strong>
                    <small>{cardPreview(card)}</small>
                  </span>
                </summary>
                <div className="digest-card-body">
                  {card.blocks.map(renderBlock)}
                </div>
              </details>
            ))}
          </div>
        </details>
      ))}
    </div>
  );
}

function MetricCard({ label, value }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function BarList({ data }) {
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, value]) => value));

  if (!entries.length) return <div className="placeholder">No participant data found.</div>;

  return (
    <div className="bar-list">
      {entries.map(([label, value]) => (
        <div className="bar-row" key={label}>
          <div className="bar-label">{label}</div>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${Math.max(8, (value / max) * 100)}%` }} />
          </div>
          <div className="bar-value">{value}</div>
        </div>
      ))}
    </div>
  );
}

function TopicCard({ topic, index }) {
  return (
    <article className="topic-card">
      <div className="topic-card-header">
        <div>
          <span className="topic-kicker">Topic {index + 1}</span>
          <h3>{topic.topic_summary || "Untitled topic"}</h3>
        </div>
        <span className="topic-count">{(topic.sample_messages || []).length} samples</span>
      </div>

      <div className="chip-row">
        {(topic.keywords || []).map((keyword) => (
          <span className="keyword-chip" key={keyword}>{keyword}</span>
        ))}
      </div>

      <div className="quote-list">
        {(topic.sample_messages || []).map((message, messageIndex) => (
          <blockquote key={messageIndex}>{message}</blockquote>
        ))}
      </div>
    </article>
  );
}

function MessageResult({ item }) {
  return (
    <article className="message-result">
      <div className="message-meta">
        <strong>{item.chat_name || item.user || "Current chat"}</strong>
        <span>{[item.date, item.user].filter(Boolean).join(" | ") || "Source message"}</span>
      </div>
      <blockquote>{item.raw || item.text}</blockquote>
    </article>
  );
}

function App() {
  const [chat, setChat] = useState("");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [model, setModel] = useState("accurate");
  const [lastN, setLastN] = useState(0);
  const [statusMsg, setStatusMsg] = useState("");
  const [summaryMode, setSummaryMode] = useState("normal");
  const [evidenceMode, setEvidenceMode] = useState(true);
  const [question, setQuestion] = useState("");
  const [askLoading, setAskLoading] = useState(false);
  const [answer, setAnswer] = useState("");
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analytics, setAnalytics] = useState(null);
  const [topicsLoading, setTopicsLoading] = useState(false);
  const [topics, setTopics] = useState([]);
  const [memoryLoading, setMemoryLoading] = useState(false);
  const [memory, setMemory] = useState(null);
  const [memoryName, setMemoryName] = useState("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [noiseLoading, setNoiseLoading] = useState(false);
  const [noiseItems, setNoiseItems] = useState([]);
  const [explainLoading, setExplainLoading] = useState(false);
  const [explanation, setExplanation] = useState("");
  const [explainEvidence, setExplainEvidence] = useState([]);
  const [activeTab, setActiveTab] = useState("summary");
  const [fileInfo, setFileInfo] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(true);
  const [workflowStep, setWorkflowStep] = useState("");
  const fileInputRef = useRef(null);

  const busy = loading || askLoading || analyticsLoading || topicsLoading || memoryLoading || searchLoading || noiseLoading || explainLoading;
  const stats = useMemo(() => parseChatStats(chat), [chat]);
  const canSummarize = useMemo(() => chat.trim().length > 0 && !loading, [chat, loading]);
  const canAsk = useMemo(() => summary.trim().length > 0 && question.trim().length > 0 && !askLoading, [summary, question, askLoading]);
  const canAnalyze = useMemo(() => chat.trim().length > 0 && !analyticsLoading, [chat, analyticsLoading]);
  const canDetectTopics = useMemo(() => chat.trim().length > 0 && !topicsLoading, [chat, topicsLoading]);

  useEffect(() => {
    if (activeTab === "memory" && !memory && !memoryLoading) {
      loadMemory();
    }
  }, [activeTab, memory, memoryLoading]);

  async function summarizeChat() {
    if (!chat.trim()) return;

    setLoading(true);
    setSummary("");
    setCopied(false);
    setStatusMsg("");
    setAnswer("");
    setQuestion("");
    setWorkflowStep("Cleaning chat");
    setActiveTab("summary");

    try {
      setWorkflowStep("Sending chat to local model");
      const res = await fetch(`${API_BASE}/summarize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_text: chat,
          model,
          last_n: Number(lastN) || 0,
          mode: summaryMode,
          evidence: evidenceMode
        })
      });

      setWorkflowStep("Formatting summary");
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
      setWorkflowStep("");
    }
  }

  async function askMyChat() {
    if (!summary.trim() || !question.trim()) return;

    setAskLoading(true);
    setAnswer("");
    setStatusMsg("");
    setWorkflowStep("Finding answer in chat");

    try {
      const res = await fetch(`${API_BASE}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_text: chat, summary, question, model })
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
      setWorkflowStep("");
    }
  }

  async function analyzeChat() {
    if (!chat.trim()) return;

    setAnalyticsLoading(true);
    setStatusMsg("");
    setAnalytics(null);
    setActiveTab("analytics");
    setWorkflowStep("Crunching chat statistics");

    try {
      const res = await fetch(`${API_BASE}/analytics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_text: chat, last_n: Number(lastN) || 0 })
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
      setWorkflowStep("");
    }
  }

  async function detectTopics() {
    if (!chat.trim()) return;

    setTopicsLoading(true);
    setStatusMsg("");
    setTopics([]);
    setActiveTab("topics");
    setWorkflowStep("Clustering related messages");

    try {
      const res = await fetch(`${API_BASE}/topics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_text: chat,
          last_n: Number(lastN) || 0,
          max_topics: 7,
          chunk_size: 200,
          sample_per_topic: 3,
          model: "fast"
        })
      });

      const data = await res.json();
      if (!res.ok) {
        setTopics([]);
        setStatusMsg(data?.detail || "Error detecting topics.");
        return;
      }

      setTopics(data.topics || []);
      if (!data.topics || data.topics.length === 0) {
        setStatusMsg("No topics found. Try pasting more messages.");
      }
    } catch (e) {
      console.error(e);
      setTopics([]);
      setStatusMsg("Error detecting topics.");
    } finally {
      setTopicsLoading(false);
      setWorkflowStep("");
    }
  }

  async function loadMemory() {
    setMemoryLoading(true);
    setStatusMsg("");
    setWorkflowStep("Loading local memory");

    try {
      const res = await fetch(`${API_BASE}/memory`);
      const data = await res.json();
      if (!res.ok) {
        setStatusMsg(data?.detail || "Error loading memory.");
        return;
      }
      setMemory(data);
    } catch (e) {
      console.error(e);
      setStatusMsg("Error loading memory.");
    } finally {
      setMemoryLoading(false);
      setWorkflowStep("");
    }
  }

  async function saveToMemory() {
    if (!chat.trim()) return;

    setMemoryLoading(true);
    setStatusMsg("");
    setActiveTab("memory");
    setWorkflowStep("Saving chat locally");

    try {
      const res = await fetch(`${API_BASE}/memory/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          chat_text: chat,
          name: memoryName.trim() || fileInfo?.name || "Saved chat"
        })
      });

      const data = await res.json();
      if (!res.ok || data.error) {
        setStatusMsg(data?.error || data?.detail || "Error saving chat memory.");
        return;
      }

      setStatusMsg(`Saved ${data.message_count} messages to local memory.`);
      setMemoryName("");
      await loadMemory();
    } catch (e) {
      console.error(e);
      setStatusMsg("Error saving chat memory.");
    } finally {
      setMemoryLoading(false);
      setWorkflowStep("");
    }
  }

  async function searchMemory() {
    if (!searchQuery.trim()) return;

    setSearchLoading(true);
    setStatusMsg("");
    setActiveTab("search");
    setWorkflowStep("Searching saved and current chats");

    try {
      const res = await fetch(`${API_BASE}/memory/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: searchQuery,
          chat_text: chat,
          limit: 12
        })
      });

      const data = await res.json();
      if (!res.ok) {
        setSearchResults([]);
        setStatusMsg(data?.detail || "Error searching memory.");
        return;
      }

      setSearchResults(data.matches || []);
    } catch (e) {
      console.error(e);
      setSearchResults([]);
      setStatusMsg("Error searching memory.");
    } finally {
      setSearchLoading(false);
      setWorkflowStep("");
    }
  }

  async function runNoiseKiller() {
    if (!chat.trim()) return;

    setNoiseLoading(true);
    setStatusMsg("");
    setNoiseItems([]);
    setActiveTab("noise");
    setWorkflowStep("Keeping only important messages");

    try {
      const res = await fetch(`${API_BASE}/noise`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_text: chat, limit: 30 })
      });

      const data = await res.json();
      if (!res.ok) {
        setStatusMsg(data?.detail || "Error filtering chat.");
        return;
      }
      setNoiseItems(data.important_messages || []);
    } catch (e) {
      console.error(e);
      setStatusMsg("Error filtering chat.");
    } finally {
      setNoiseLoading(false);
      setWorkflowStep("");
    }
  }

  async function explainCurrentChat() {
    if (!chat.trim()) return;

    setExplainLoading(true);
    setStatusMsg("");
    setExplanation("");
    setExplainEvidence([]);
    setActiveTab("explain");
    setWorkflowStep("Explaining confusing context");

    try {
      const res = await fetch(`${API_BASE}/explain`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_text: chat, model })
      });

      const data = await res.json();
      if (!res.ok) {
        setStatusMsg(data?.detail || "Error explaining chat.");
        return;
      }
      setExplanation(data.explanation || "");
      setExplainEvidence(data.evidence || []);
    } catch (e) {
      console.error(e);
      setStatusMsg("Error explaining chat.");
    } finally {
      setExplainLoading(false);
      setWorkflowStep("");
    }
  }

  function copySummary() {
    if (!summary) return;
    navigator.clipboard.writeText(summary);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  function downloadText(content, fileName, type = "text/plain") {
    if (!content) return;
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName;
    a.click();
    URL.revokeObjectURL(url);
  }

  function exportSummary(format) {
    if (!summary) return;
    if (format === "json") {
      downloadText(JSON.stringify({ summary, answer, analytics, topics }, null, 2), "chat-summary.json", "application/json");
    } else if (format === "md") {
      downloadText(`# Chat Summary\n\n${summary}`, "chat-summary.md", "text/markdown");
    } else if (format === "actions") {
      downloadText(extractActionItems(summary), "chat-action-items.txt");
    } else {
      downloadText(summary, "chat-summary.txt");
    }
  }

  async function loadZipFile(file) {
    if (!file) return;

    setStatusMsg("");
    setSummary("");
    setCopied(false);
    setAnswer("");
    setQuestion("");
    setAnalytics(null);
    setTopics([]);
    setWorkflowStep("Reading ZIP");

    try {
      const arrayBuffer = await file.arrayBuffer();
      const zip = await JSZip.loadAsync(arrayBuffer);
      const txtFiles = [];

      zip.forEach((relativePath, zipEntry) => {
        if (!zipEntry.dir && relativePath.toLowerCase().endsWith(".txt")) {
          txtFiles.push(zipEntry);
        }
      });

      if (txtFiles.length === 0) {
        setStatusMsg("No .txt file found inside ZIP. Export chat again without media.");
        return;
      }

      setWorkflowStep("Choosing chat text file");
      let bestFile = null;
      let bestSize = -1;

      for (const entry of txtFiles) {
        const content = await entry.async("string");
        if (content.length > bestSize) {
          bestSize = content.length;
          bestFile = { entry, content };
        }
      }

      if (!bestFile) {
        setStatusMsg("Could not read chat text from ZIP.");
        return;
      }

      setChat(bestFile.content);
      setFileInfo({ name: bestFile.entry.name, size: formatBytes(file.size) });
      setStatusMsg(`Loaded ${bestFile.entry.name}`);
    } catch (err) {
      console.error(err);
      setStatusMsg("Failed to read ZIP. Try exporting again.");
    } finally {
      setWorkflowStep("");
    }
  }

  function handleZipUpload(e) {
    loadZipFile(e.target.files?.[0]);
    e.target.value = "";
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragActive(false);
    loadZipFile(e.dataTransfer.files?.[0]);
  }

  function clearAll() {
    setChat("");
    setSummary("");
    setStatusMsg("");
    setCopied(false);
    setQuestion("");
    setAnswer("");
    setAnalytics(null);
    setTopics([]);
    setSearchResults([]);
    setNoiseItems([]);
    setExplanation("");
    setExplainEvidence([]);
    setFileInfo(null);
    setWorkflowStep("");
    setActiveTab("summary");
  }

  return (
    <div className="page">
      <header className="topbar">
        <div className="brand">
          <div className="logo">CS</div>
          <div>
            <div className="title">Chat Summarizer</div>
            <div className="subtitle">Paste unread chats or import a WhatsApp ZIP</div>
          </div>
        </div>
      </header>

      <main className="container">
        <section className="panel input-panel">
          <header className="panel-header split">
            <div>
              <div className="panel-title">Chat Input</div>
              <div className="panel-note">Local summarization for long conversations</div>
            </div>

            <button className="small-btn" type="button" onClick={() => setSettingsOpen((open) => !open)}>
              {settingsOpen ? "Hide settings" : "Show settings"}
            </button>
          </header>

          {settingsOpen && (
            <div className="settings-grid">
              <label>
                Model
                <select className="select" value={model} onChange={(e) => setModel(e.target.value)} disabled={busy}>
                  <option value="fast">Fast</option>
                  <option value="accurate">Accurate</option>
                </select>
              </label>

              <label>
                Summary style
                <select className="select" value={summaryMode} onChange={(e) => setSummaryMode(e.target.value)} disabled={busy}>
                  <option value="normal">Normal</option>
                  <option value="tldr">TLDR, 2 lines</option>
                  <option value="bullets">Bullet summary</option>
                  <option value="minutes">Meeting minutes</option>
                </select>
              </label>

              <label>
                Last N
                <input className="input" type="number" min="0" placeholder="0 = all" value={lastN} onChange={(e) => setLastN(e.target.value)} disabled={busy} />
              </label>

              <label className="toggle-row">
                <input type="checkbox" checked={evidenceMode} onChange={(e) => setEvidenceMode(e.target.checked)} disabled={busy} />
                <span>Evidence mode</span>
              </label>
            </div>
          )}

          <div className="stats-row">
            <MetricCard label="Messages" value={stats.messages} />
            <MetricCard label="Participants" value={stats.participants || "-"} />
            <MetricCard label="Last message" value={stats.lastMessage} />
            <MetricCard label="Estimate" value={stats.estimate ? `${stats.estimate} min` : "-"} />
          </div>

          <div
            className={`dropzone ${dragActive ? "is-dragging" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input ref={fileInputRef} type="file" accept=".zip" onChange={handleZipUpload} />
            <strong>Drop WhatsApp ZIP here</strong>
            <span>{fileInfo ? `${fileInfo.name} (${fileInfo.size})` : "or click to choose a ZIP exported without media"}</span>
          </div>

          <div className="privacy-strip">
            <strong>Private local memory</strong>
            <span>Chats stay on this laptop. Save class, placement, and group exports, then search them later.</span>
          </div>

          <textarea
            className="textarea"
            value={chat}
            onChange={(e) => {
              setChat(e.target.value);
              setFileInfo(null);
            }}
            placeholder="Paste unread chat messages here..."
            disabled={busy}
          />

          <footer className="panel-footer">
            <button className="primary-btn" onClick={summarizeChat} disabled={!canSummarize}>
              {loading ? "Summarizing..." : "Summarize"}
            </button>
            <button className="secondary-btn" onClick={analyzeChat} disabled={!canAnalyze}>
              {analyticsLoading ? "Analyzing..." : "Analyze"}
            </button>
            <button className="secondary-btn" onClick={detectTopics} disabled={!canDetectTopics}>
              {topicsLoading ? "Detecting..." : "Detect topics"}
            </button>
            <button className="secondary-btn" onClick={runNoiseKiller} disabled={!chat.trim() || noiseLoading}>
              {noiseLoading ? "Filtering..." : "Important only"}
            </button>
            <button className="secondary-btn" onClick={explainCurrentChat} disabled={!chat.trim() || explainLoading}>
              {explainLoading ? "Explaining..." : "Explain"}
            </button>
            <button className="secondary-btn" onClick={clearAll} disabled={busy}>
              Clear
            </button>
          </footer>

          {(statusMsg || workflowStep) && (
            <div className="status">
              {workflowStep && <span className="status-pulse" />}
              {workflowStep || statusMsg}
            </div>
          )}
        </section>

        <section className="panel results-panel">
          <header className="panel-header">
            <div className="tabs" role="tablist" aria-label="Result views">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  className={activeTab === tab.id ? "tab active" : "tab"}
                  onClick={() => setActiveTab(tab.id)}
                  type="button"
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </header>

          {activeTab === "summary" && (
            <div className="actions-row">
              <button className="small-btn" onClick={copySummary} disabled={!summary}>
                {copied ? "Copied" : "Copy"}
              </button>
              <select className="small-select" value="" onChange={(e) => exportSummary(e.target.value)} disabled={!summary}>
                <option value="" disabled>Export</option>
                <option value="txt">Text</option>
                <option value="md">Markdown</option>
                <option value="json">JSON</option>
                <option value="actions">Actions only</option>
              </select>
            </div>
          )}

          {activeTab === "summary" && (
            <div className="output main-output">
              {!summary && !loading && <div className="placeholder">Your structured summary will appear here.</div>}
              {loading && <div className="placeholder">{workflowStep || "Thinking..."}</div>}
              {summary && <DigestText text={summary} />}
            </div>
          )}

          {activeTab === "ask" && (
            <div className="tab-body">
              <div className="ask-row">
                <input
                  className="question-input"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder='Ask something like "What decision did they make?"'
                  disabled={!summary || loading || askLoading || analyticsLoading || topicsLoading}
                />
                <button className="primary-btn" onClick={askMyChat} disabled={!canAsk}>
                  {askLoading ? "Answering..." : "Ask"}
                </button>
              </div>

              <div className="output main-output">
                {!answer && !askLoading && <div className="placeholder">Answers use only the chat text.</div>}
                {askLoading && <div className="placeholder">{workflowStep || "Thinking..."}</div>}
                {answer && <DigestText text={answer} />}
              </div>
            </div>
          )}

          {activeTab === "analytics" && (
            <div className="tab-body">
              {!analytics && !analyticsLoading && <div className="placeholder">Click Analyze to see chat statistics.</div>}
              {analyticsLoading && <div className="placeholder">{workflowStep || "Crunching numbers..."}</div>}
              {analytics && (
                <>
                  <div className="stats-row result-stats">
                    <MetricCard label="Total messages" value={analytics.total_messages} />
                    <MetricCard label="Top sender" value={Object.entries(analytics.messages_per_user || {}).sort((a, b) => b[1] - a[1])[0]?.[0] || "-"} />
                    <MetricCard label="Most active day" value={analytics.most_active_day || "No dates in chat"} />
                    <MetricCard label="Peak hour" value={analytics.most_active_hour || "No times in chat"} />
                  </div>

                  <div className="output chart-output">
                    <h3>Messages per user</h3>
                    <BarList data={analytics.messages_per_user} />

                    <h3>Top words</h3>
                    <div className="chip-row">
                      {(analytics.top_words || []).map((item) => {
                        const word = normalizeTopWord(item);
                        return <span className="keyword-chip" key={word.word}>{word.word} ({word.count})</span>;
                      })}
                      {(!analytics.top_words || analytics.top_words.length === 0) && <span className="placeholder">No useful words found.</span>}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {activeTab === "topics" && (
            <div className="tab-body topic-list">
              {topicsLoading && <div className="placeholder">{workflowStep || "Detecting topics..."}</div>}
              {!topicsLoading && topics.length === 0 && <div className="placeholder">Click Detect topics to cluster the chat into themes.</div>}
              {!topicsLoading && topics.map((topic, index) => (
                <TopicCard key={`${topic.chunk_id}-${topic.topic_id}-${index}`} topic={topic} index={index} />
              ))}
            </div>
          )}

          {activeTab === "memory" && (
            <div className="tab-body">
              <div className="memory-actions">
                <input
                  className="question-input"
                  value={memoryName}
                  onChange={(e) => setMemoryName(e.target.value)}
                  placeholder="Name this chat, e.g. ECE placement group"
                  disabled={busy}
                />
                <button className="primary-btn" onClick={saveToMemory} disabled={!chat.trim() || memoryLoading}>
                  Save current chat
                </button>
                <button className="secondary-btn" onClick={loadMemory} disabled={memoryLoading}>
                  Refresh
                </button>
              </div>

              {!memory && !memoryLoading && <div className="placeholder">Save chats here to build a private searchable memory.</div>}
              {memoryLoading && <div className="placeholder">{workflowStep || "Loading memory..."}</div>}
              {memory && (
                <div className="output chart-output">
                  <div className="stats-row result-stats">
                    <MetricCard label="Saved chats" value={memory.summary?.chat_count || 0} />
                    <MetricCard label="Messages" value={memory.summary?.total_messages || 0} />
                    <MetricCard label="People" value={memory.summary?.participants?.length || 0} />
                    <MetricCard label="Dates" value={memory.summary?.date_count || 0} />
                  </div>

                  <div className="memory-list">
                    {(memory.chats || []).map((item) => (
                      <article className="memory-card" key={item.id}>
                        <h3>{item.name}</h3>
                        <p>{item.message_count} messages | {(item.participants || []).slice(0, 4).join(", ") || "No named participants"}</p>
                        <small>{(item.dates || []).slice(0, 3).join(", ") || "No dates found"}</small>
                      </article>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === "search" && (
            <div className="tab-body">
              <div className="ask-row">
                <input
                  className="question-input"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") searchMemory();
                  }}
                  placeholder='Search "hall ticket", "placement coordinator", "patent filing"...'
                  disabled={searchLoading}
                />
                <button className="primary-btn" onClick={searchMemory} disabled={!searchQuery.trim() || searchLoading}>
                  {searchLoading ? "Searching..." : "Search"}
                </button>
              </div>

              <div className="output main-output result-list">
                {!searchResults.length && !searchLoading && <div className="placeholder">Search the current chat plus saved local memory.</div>}
                {searchLoading && <div className="placeholder">{workflowStep || "Searching..."}</div>}
                {searchResults.map((item, index) => <MessageResult item={item} key={`${item.chat_id}-${index}`} />)}
              </div>
            </div>
          )}

          {activeTab === "noise" && (
            <div className="tab-body">
              <div className="panel-note">Noise Killer hides greetings, thanks, and filler so important college/group messages stand out.</div>
              <div className="output main-output result-list">
                {!noiseItems.length && !noiseLoading && <div className="placeholder">Click Important only to extract the useful messages.</div>}
                {noiseLoading && <div className="placeholder">{workflowStep || "Filtering..."}</div>}
                {noiseItems.map((item, index) => <MessageResult item={{ ...item, chat_name: `Score ${item.score}` }} key={index} />)}
              </div>
            </div>
          )}

          {activeTab === "explain" && (
            <div className="tab-body">
              <div className="output main-output">
                {!explanation && !explainLoading && <div className="placeholder">Click Explain to understand what is going on in a messy chat.</div>}
                {explainLoading && <div className="placeholder">{workflowStep || "Explaining..."}</div>}
                {explanation && (
                  <>
                    <DigestText text={explanation} />
                    <h3 className="evidence-title">Evidence used</h3>
                    <div className="result-list">
                      {explainEvidence.map((item, index) => <MessageResult item={{ ...item, chat_name: `Evidence ${index + 1}` }} key={index} />)}
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
