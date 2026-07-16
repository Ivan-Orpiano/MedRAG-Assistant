"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import Modal from "@/components/Modal";
import PageFrame from "@/components/PageFrame";
import { apiErrorDetail, del, getJson, patchJson, uploadDocument } from "@/lib/api";
import { CATEGORIES } from "@/lib/settings";

const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt"];
const MAX_FILE_SIZE = 50 * 1024 * 1024;

const STATUS_COLORS: Record<string, string> = {
  indexed: "bg-green-600",
  processing: "bg-amber-500",
  pending: "bg-gray-400",
  failed: "bg-red-600",
  superseded: "bg-gray-300 text-gray-700",
};

interface DocumentVersion {
  version_number: number;
  status: string;
  error?: string | null;
  chunk_count?: number | null;
  page_count?: number | null;
  ocr_pages?: number | null;
}

interface Doc {
  id: string;
  title: string;
  category: string;
  description?: string | null;
  tags?: string[] | null;
  versions: DocumentVersion[];
}

function isAccepted(name: string): boolean {
  const lower = name.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export default function DocumentsPage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [filterCategory, setFilterCategory] = useState("");
  const [notice, setNotice] = useState<{ text: string; kind: "ok" | "err" } | null>(null);

  // upload form
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("clinical_guideline");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [uploadStatus, setUploadStatus] = useState<{ text: string; kind: "ok" | "err" } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // dialogs
  const [versionTarget, setVersionTarget] = useState<Doc | null>(null);
  const [editTarget, setEditTarget] = useState<Doc | null>(null);
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);

  const refreshList = useCallback(async (categoryFilter: string) => {
    try {
      const params = categoryFilter ? { category: categoryFilter } : undefined;
      setDocs(await getJson("/api/v1/documents", params));
    } catch {
      setNotice({ text: "Could not load documents", kind: "err" });
    }
  }, []);

  useEffect(() => {
    refreshList(filterCategory);
  }, [filterCategory, refreshList]);

  const handleUpload = async (file: File) => {
    if (!title.trim()) {
      setUploadStatus({ text: "Please set a title before uploading.", kind: "err" });
      return;
    }
    if (!isAccepted(file.name)) {
      setUploadStatus({ text: "Only PDF, DOCX, and TXT are supported.", kind: "err" });
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      setUploadStatus({ text: "File exceeds the 50 MB limit.", kind: "err" });
      return;
    }
    try {
      await uploadDocument(
        { title: title.trim(), category, description, tags },
        file,
      );
    } catch (err) {
      setUploadStatus({ text: apiErrorDetail(err), kind: "err" });
      return;
    }
    setUploadStatus({ text: `Uploaded '${file.name}' — indexing has been queued.`, kind: "ok" });
    setTitle("");
    refreshList(filterCategory);
  };

  const handleNewVersion = async (doc: Doc, file: File) => {
    if (!isAccepted(file.name)) {
      setNotice({ text: "Unsupported file type", kind: "err" });
      return;
    }
    try {
      await uploadDocument({}, file, `/api/v1/documents/${doc.id}/versions`);
      setNotice({ text: "New version queued for indexing", kind: "ok" });
      setVersionTarget(null);
      refreshList(filterCategory);
    } catch (err) {
      setNotice({ text: apiErrorDetail(err), kind: "err" });
    }
  };

  const handleDelete = async (doc: Doc) => {
    setMenuOpenId(null);
    try {
      await del(`/api/v1/documents/${doc.id}`);
      setNotice({ text: "Document deleted; vectors are being purged", kind: "ok" });
      refreshList(filterCategory);
    } catch (err) {
      setNotice({ text: apiErrorDetail(err), kind: "err" });
    }
  };

  const inputClass =
    "rounded border border-gray-300 p-2 text-sm focus:border-blue-600 focus:outline-none";

  return (
    <PageFrame title="Document library" active="documents">
      {notice && (
        <p className={`text-sm ${notice.kind === "ok" ? "text-green-700" : "text-red-600"}`}>
          {notice.text}
        </p>
      )}

      {/* ---- upload card ---- */}
      <section className="flex w-full flex-col gap-2 rounded-lg bg-white p-4 shadow">
        <h2 className="font-bold">Upload a document</h2>
        <div className="flex w-full items-center gap-2">
          <input
            placeholder="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={`grow ${inputClass}`}
          />
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className={`w-60 ${inputClass}`}
          >
            {Object.entries(CATEGORIES).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex w-full items-center gap-2">
          <input
            placeholder="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className={`grow ${inputClass}`}
          />
          <input
            placeholder="Tags, comma-separated"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            className={`w-60 ${inputClass}`}
          />
        </div>
        {uploadStatus && (
          <p className={`text-sm ${uploadStatus.kind === "ok" ? "text-green-700" : "text-red-600"}`}>
            {uploadStatus.text}
          </p>
        )}
        <label
          className="flex w-full cursor-pointer items-center justify-center rounded border-2 border-dashed border-gray-300 p-6 text-sm text-gray-500 hover:border-blue-500 hover:text-blue-600"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file) handleUpload(file);
          }}
        >
          Drop PDF / DOCX / TXT here or click to browse
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleUpload(file);
              e.target.value = "";
            }}
          />
        </label>
      </section>

      {/* ---- library ---- */}
      <div className="flex w-full items-center gap-2">
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
          className={`w-60 ${inputClass}`}
        >
          <option value="">All categories</option>
          {Object.entries(CATEGORIES).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <button
          onClick={() => refreshList(filterCategory)}
          className="rounded px-3 py-2 text-sm text-blue-700 hover:bg-blue-50"
        >
          ↻ Refresh
        </button>
      </div>

      <div className="flex w-full flex-col gap-2">
        {docs.length === 0 && <p className="text-gray-500">No documents yet.</p>}
        {docs.map((doc) => {
          const latest = doc.versions.length ? doc.versions[doc.versions.length - 1] : null;
          return (
            <article key={doc.id} className="w-full rounded-lg bg-white p-4 shadow">
              <div className="flex w-full items-center gap-2">
                <span className="grow font-bold">{doc.title}</span>
                <span className="rounded bg-blue-800 px-2 py-0.5 text-xs text-white">
                  {CATEGORIES[doc.category] ?? doc.category}
                </span>
                {latest && (
                  <span
                    className={`rounded px-2 py-0.5 text-xs text-white ${
                      STATUS_COLORS[latest.status] ?? "bg-gray-400"
                    }`}
                  >
                    v{latest.version_number} · {latest.status}
                  </span>
                )}
                <div className="relative">
                  <button
                    onClick={() => setMenuOpenId(menuOpenId === doc.id ? null : doc.id)}
                    className="rounded-full px-2 py-1 hover:bg-gray-100"
                    aria-label="Actions"
                  >
                    ⋮
                  </button>
                  {menuOpenId === doc.id && (
                    <div className="absolute right-0 z-10 mt-1 w-48 rounded border border-gray-200 bg-white py-1 shadow-lg">
                      <button
                        className="block w-full px-3 py-1.5 text-left text-sm hover:bg-gray-100"
                        onClick={() => {
                          setMenuOpenId(null);
                          setVersionTarget(doc);
                        }}
                      >
                        Upload new version
                      </button>
                      <button
                        className="block w-full px-3 py-1.5 text-left text-sm hover:bg-gray-100"
                        onClick={() => {
                          setMenuOpenId(null);
                          setEditTarget(doc);
                        }}
                      >
                        Edit metadata
                      </button>
                      <button
                        className="block w-full px-3 py-1.5 text-left text-sm text-red-600 hover:bg-gray-100"
                        onClick={() => handleDelete(doc)}
                      >
                        Delete (admin)
                      </button>
                    </div>
                  )}
                </div>
              </div>
              {doc.description && <p className="text-sm text-gray-600">{doc.description}</p>}
              {doc.tags && doc.tags.length > 0 && (
                <div className="mt-1 flex gap-1">
                  {doc.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded border border-gray-400 px-2 py-0.5 text-xs text-gray-600"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              {latest?.status === "failed" && (
                <p className="mt-1 text-xs text-red-600">Indexing failed: {latest.error}</p>
              )}
              {latest?.status === "indexed" && (
                <p className="mt-1 text-xs text-gray-500">
                  {latest.chunk_count} chunks, {latest.page_count} pages
                  {latest.ocr_pages ? `, ${latest.ocr_pages} OCR pages` : ""}
                </p>
              )}
            </article>
          );
        })}
      </div>

      {versionTarget && (
        <Modal title={`New version of '${versionTarget.title}'`} onClose={() => setVersionTarget(null)}>
          <input
            type="file"
            accept=".pdf,.docx,.txt"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleNewVersion(versionTarget, file);
            }}
          />
        </Modal>
      )}

      {editTarget && (
        <EditDialog
          doc={editTarget}
          onClose={() => setEditTarget(null)}
          onSaved={() => {
            setEditTarget(null);
            refreshList(filterCategory);
          }}
          onError={(text) => setNotice({ text, kind: "err" })}
        />
      )}
    </PageFrame>
  );
}

function EditDialog({
  doc,
  onClose,
  onSaved,
  onError,
}: {
  doc: Doc;
  onClose: () => void;
  onSaved: () => void;
  onError: (text: string) => void;
}) {
  const [title, setTitle] = useState(doc.title);
  const [description, setDescription] = useState(doc.description ?? "");
  const [category, setCategory] = useState(doc.category);
  const [tags, setTags] = useState((doc.tags ?? []).join(", "));

  const inputClass =
    "w-full rounded border border-gray-300 p-2 text-sm focus:border-blue-600 focus:outline-none";

  const save = async () => {
    try {
      await patchJson(`/api/v1/documents/${doc.id}`, {
        title,
        description,
        category,
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
      });
      onSaved();
    } catch (err) {
      onError(apiErrorDetail(err));
    }
  };

  return (
    <Modal title="Edit metadata" onClose={onClose}>
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" className={inputClass} />
      <input
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Description"
        className={inputClass}
      />
      <select value={category} onChange={(e) => setCategory(e.target.value)} className={inputClass}>
        {Object.entries(CATEGORIES).map(([key, label]) => (
          <option key={key} value={key}>
            {label}
          </option>
        ))}
      </select>
      <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="Tags" className={inputClass} />
      <button onClick={save} className="rounded bg-blue-700 p-2 text-sm font-medium text-white hover:bg-blue-800">
        Save
      </button>
    </Modal>
  );
}
