"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import PageFrame from "@/components/PageFrame";
import { apiErrorDetail, chatStream, getJson } from "@/lib/api";
import { CATEGORIES } from "@/lib/settings";

interface Citation {
  marker: string;
  document_title: string;
  version_number: number;
  page_number?: number | null;
  section?: string | null;
  excerpt: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const conversationId = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // filters
  const [categories, setCategories] = useState<string[]>([]);
  const [documents, setDocuments] = useState<Array<{ id: string; title: string }>>([]);
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const [tags, setTags] = useState("");
  const [after, setAfter] = useState("");
  const [before, setBefore] = useState("");
  const [topK, setTopK] = useState(8);

  useEffect(() => {
    getJson("/api/v1/documents")
      .then((docs: Array<{ id: string; title: string }>) =>
        setDocuments(docs.map((d) => ({ id: d.id, title: d.title }))),
      )
      .catch(() => {});
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const buildFilters = () => {
    const filters: Record<string, unknown> = {};
    if (categories.length) filters.categories = categories;
    if (documentIds.length) filters.document_ids = documentIds;
    const tagList = tags.split(",").map((t) => t.trim()).filter(Boolean);
    if (tagList.length) filters.tags = tagList;
    if (after) filters.uploaded_after = `${after}T00:00:00Z`;
    if (before) filters.uploaded_before = `${before}T23:59:59Z`;
    return Object.keys(filters).length ? filters : null;
  };

  const updateLastAssistant = (patch: Partial<Message>) => {
    setMessages((prev) => {
      const next = [...prev];
      next[next.length - 1] = { ...next[next.length - 1], ...patch };
      return next;
    });
  };

  const send = async () => {
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true);
    setQuestion("");
    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: "_Searching the knowledge base…_" },
    ]);
    let buffer = "";
    try {
      const payload = {
        conversation_id: conversationId.current,
        question: text,
        filters: buildFilters(),
        top_k: topK,
      };
      for await (const { event, data } of chatStream(payload)) {
        if (event === "meta") {
          conversationId.current = JSON.parse(data).conversation_id ?? null;
        } else if (event === "token") {
          buffer += data;
          updateLastAssistant({ content: buffer });
        } else if (event === "notfound") {
          updateLastAssistant({ content: `⚠️ ${data}` });
        } else if (event === "citations") {
          updateLastAssistant({ citations: JSON.parse(data) });
        } else if (event === "error") {
          updateLastAssistant({
            content: "⚠️ Something went wrong while answering. Please try again.",
          });
        }
      }
    } catch (err) {
      updateLastAssistant({ content: `⚠️ ${apiErrorDetail(err)}` });
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    conversationId.current = null;
    setMessages([]);
  };

  const toggleCategory = (key: string) =>
    setCategories((prev) =>
      prev.includes(key) ? prev.filter((c) => c !== key) : [...prev, key],
    );

  return (
    <PageFrame title="Ask the knowledge base" active="chat">
      <div className="flex w-full items-start gap-4">
        {/* ---- left: conversation ---- */}
        <div className="flex grow flex-col gap-3">
          <div className="flex max-h-[55vh] min-h-[300px] w-full flex-col gap-3 overflow-y-auto">
            {messages.map((message, i) =>
              message.role === "user" ? (
                <div
                  key={i}
                  className="max-w-[85%] self-end whitespace-pre-wrap rounded-lg bg-blue-100 p-3 shadow-sm"
                >
                  {message.content}
                </div>
              ) : (
                <div
                  key={i}
                  className="max-w-[85%] self-start rounded-lg bg-gray-50 p-3 shadow-sm"
                >
                  <div className="prose prose-sm max-w-none [&_p]:my-1">
                    <ReactMarkdown>{message.content}</ReactMarkdown>
                  </div>
                  {message.citations && message.citations.length > 0 && (
                    <details className="mt-2 rounded bg-blue-50 p-2">
                      <summary className="cursor-pointer text-sm font-medium">
                        📖 Sources ({message.citations.length})
                      </summary>
                      <div className="mt-2 flex flex-col gap-2">
                        {message.citations.map((c, j) => (
                          <div key={j}>
                            <p className="text-sm font-medium">
                              [{c.marker}] {c.document_title} (v{c.version_number}
                              {c.page_number ? `, page ${c.page_number}` : ""})
                              {c.section ? ` — ${c.section}` : ""}
                            </p>
                            <p className="whitespace-pre-wrap text-xs italic text-gray-600">
                              “{c.excerpt}”
                            </p>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
              ),
            )}
            <div ref={messagesEndRef} />
          </div>
          <div className="flex w-full items-end gap-2">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              rows={2}
              placeholder="e.g. What is the recommended anticoagulation protocol after hip replacement?"
              className="max-h-[120px] grow resize-none rounded border border-gray-300 p-2 focus:border-blue-600 focus:outline-none"
            />
            <button
              onClick={send}
              disabled={busy}
              className="rounded-full bg-blue-700 p-3 text-white hover:bg-blue-800 disabled:opacity-50"
              aria-label="Send"
            >
              ➤
            </button>
          </div>
          <div>
            <button onClick={reset} className="rounded px-2 py-1 text-sm text-blue-700 hover:bg-blue-50">
              New conversation
            </button>
          </div>
        </div>

        {/* ---- right: metadata filters ---- */}
        <aside className="flex w-72 shrink-0 flex-col gap-3 rounded-lg bg-white p-4 shadow">
          <h2 className="font-bold">Retrieval filters</h2>
          <p className="text-xs text-gray-500">Narrow the searched corpus before asking.</p>
          <fieldset className="flex flex-col gap-1">
            <legend className="mb-1 text-sm font-medium">Categories</legend>
            {Object.entries(CATEGORIES).map(([key, label]) => (
              <label key={key} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={categories.includes(key)}
                  onChange={() => toggleCategory(key)}
                />
                {label}
              </label>
            ))}
          </fieldset>
          <label className="flex flex-col gap-1 text-sm font-medium">
            Specific documents
            <select
              multiple
              value={documentIds}
              onChange={(e) =>
                setDocumentIds(Array.from(e.target.selectedOptions, (o) => o.value))
              }
              className="h-24 rounded border border-gray-300 p-1 text-sm font-normal"
            >
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm font-medium">
            Tags (comma-separated)
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              className="rounded border border-gray-300 p-1 text-sm font-normal"
            />
          </label>
          <div className="flex gap-2">
            <label className="flex grow flex-col gap-1 text-sm font-medium">
              Uploaded after
              <input
                type="date"
                value={after}
                onChange={(e) => setAfter(e.target.value)}
                className="rounded border border-gray-300 p-1 text-sm font-normal"
              />
            </label>
            <label className="flex grow flex-col gap-1 text-sm font-medium">
              Uploaded before
              <input
                type="date"
                value={before}
                onChange={(e) => setBefore(e.target.value)}
                className="rounded border border-gray-300 p-1 text-sm font-normal"
              />
            </label>
          </div>
          <label className="flex flex-col gap-1 text-sm font-medium">
            Chunks retrieved (top-k): {topK}
            <input
              type="range"
              min={2}
              max={20}
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
            />
          </label>
        </aside>
      </div>
    </PageFrame>
  );
}
