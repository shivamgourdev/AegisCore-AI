import { useState } from "react";
import { api } from "../services/api";

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    const userMsg = { role: "user", content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    try {
      const res = await api.post("/chat/message", { message: input });
      setMessages((prev) => [...prev, { role: "assistant", content: res.data?.answer ?? "" }]);
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "Error: unable to reach API" }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-4">
      <h1 className="text-2xl font-semibold mb-4">AegisCore AI — Chat</h1>
      <form onSubmit={handleSend} className="flex gap-2 mb-4">
        <input
          className="flex-1 border rounded px-3 py-2"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about your documents..."
          disabled={loading}
        />
        <button type="submit" disabled={loading} className="px-4 py-2 bg-slate-800 text-white rounded disabled:opacity-50">
          Send
        </button>
      </form>
      <div className="space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={`p-3 rounded ${m.role === "user" ? "bg-blue-100 text-right ml-8" : "bg-slate-100"}`}>
            {m.content}
          </div>
        ))}
      </div>
      {loading && <p className="text-sm text-slate-500">Thinking…</p>}
    </div>
  );
}
