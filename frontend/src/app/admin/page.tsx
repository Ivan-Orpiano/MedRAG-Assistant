"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import PageFrame from "@/components/PageFrame";
import { ApiError, apiErrorDetail, getJson, postJson } from "@/lib/api";

interface Stats {
  documents: number;
  chunks: number;
  users: number;
  answers_grounded: number;
  answers_refused_ungrounded: number;
  avg_answer_latency_ms: number | null;
  versions_by_status: Record<string, number>;
}

interface IndexingRow {
  version_id: string;
  title: string;
  version: number;
  status: string;
  chunks: number | null;
  ocr_pages: number | null;
  created_at: string;
  error: string | null;
}

interface UserRow {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

export default function AdminPage() {
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [indexing, setIndexing] = useState<IndexingRow[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [notice, setNotice] = useState<{ text: string; kind: "ok" | "err" } | null>(null);

  // create-user form
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("researcher");

  const refresh = useCallback(async () => {
    try {
      const [statsData, indexingData, usersData] = await Promise.all([
        getJson("/api/v1/admin/stats"),
        getJson("/api/v1/admin/indexing"),
        getJson("/api/v1/auth/users"),
      ]);
      setStats(statsData);
      setIndexing(indexingData);
      setUsers(usersData);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        router.replace("/");
      }
    }
  }, [router]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 10_000);
    return () => clearInterval(timer);
  }, [refresh]);

  const createUser = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await postJson("/api/v1/auth/users", {
        email,
        full_name: fullName,
        password,
        role,
      });
      setNotice({ text: "User created", kind: "ok" });
      setEmail("");
      setFullName("");
      setPassword("");
      refresh();
    } catch (err) {
      setNotice({ text: apiErrorDetail(err), kind: "err" });
    }
  };

  const inputClass =
    "rounded border border-gray-300 p-2 text-sm focus:border-blue-600 focus:outline-none";
  const thClass = "border-b border-gray-200 px-3 py-2 text-left text-xs font-semibold uppercase text-gray-500";
  const tdClass = "border-b border-gray-100 px-3 py-2 text-sm";

  const statCards: Array<[string, number | null]> = stats
    ? [
        ["Documents", stats.documents],
        ["Indexed chunks", stats.chunks],
        ["Users", stats.users],
        ["Grounded answers", stats.answers_grounded],
        ["Refused (not in corpus)", stats.answers_refused_ungrounded],
        ["Avg latency (ms)", stats.avg_answer_latency_ms],
        ...Object.entries(stats.versions_by_status).map(
          ([status, count]): [string, number | null] => [`Versions: ${status}`, count],
        ),
      ]
    : [];

  return (
    <PageFrame title="Admin dashboard" active="admin">
      {notice && (
        <p className={`text-sm ${notice.kind === "ok" ? "text-green-700" : "text-red-600"}`}>
          {notice.text}
        </p>
      )}

      <div className="flex w-full flex-wrap gap-4">
        {statCards.map(([label, value]) => (
          <div key={label} className="flex min-w-40 flex-col items-center rounded-lg bg-white p-4 shadow">
            <span className="text-2xl font-bold">{value ?? "—"}</span>
            <span className="text-xs text-gray-500">{label}</span>
          </div>
        ))}
      </div>

      <h2 className="text-lg font-bold">Indexing activity</h2>
      <div className="w-full overflow-x-auto rounded-lg bg-white shadow">
        <table className="w-full">
          <thead>
            <tr>
              <th className={thClass}>Document</th>
              <th className={thClass}>Version</th>
              <th className={thClass}>Status</th>
              <th className={thClass}>Chunks</th>
              <th className={thClass}>OCR pages</th>
              <th className={thClass}>Uploaded</th>
              <th className={thClass}>Error</th>
            </tr>
          </thead>
          <tbody>
            {indexing.map((row) => (
              <tr key={row.version_id}>
                <td className={tdClass}>{row.title}</td>
                <td className={tdClass}>{row.version}</td>
                <td className={tdClass}>{row.status}</td>
                <td className={tdClass}>{row.chunks ?? ""}</td>
                <td className={tdClass}>{row.ocr_pages ?? ""}</td>
                <td className={tdClass}>{row.created_at}</td>
                <td className={tdClass}>{row.error ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="text-lg font-bold">User management</h2>
      <form onSubmit={createUser} className="flex w-full flex-col gap-2 rounded-lg bg-white p-4 shadow">
        <h3 className="font-bold">Create user</h3>
        <div className="flex w-full flex-wrap items-center gap-2">
          <input
            type="email"
            required
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={`grow ${inputClass}`}
          />
          <input
            required
            placeholder="Full name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className={`grow ${inputClass}`}
          />
          <input
            type="password"
            required
            minLength={10}
            placeholder="Password (min 10 chars)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={`grow ${inputClass}`}
          />
          <select value={role} onChange={(e) => setRole(e.target.value)} className={`w-48 ${inputClass}`}>
            <option value="admin">Administrator</option>
            <option value="doctor">Doctor</option>
            <option value="researcher">Researcher</option>
          </select>
          <button
            type="submit"
            className="rounded bg-blue-700 px-4 py-2 text-sm font-medium text-white hover:bg-blue-800"
          >
            Create
          </button>
        </div>
      </form>
      <div className="w-full overflow-x-auto rounded-lg bg-white shadow">
        <table className="w-full">
          <thead>
            <tr>
              <th className={thClass}>Email</th>
              <th className={thClass}>Name</th>
              <th className={thClass}>Role</th>
              <th className={thClass}>Active</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td className={tdClass}>{user.email}</td>
                <td className={tdClass}>{user.full_name}</td>
                <td className={tdClass}>{user.role}</td>
                <td className={tdClass}>{user.is_active ? "true" : "false"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PageFrame>
  );
}
