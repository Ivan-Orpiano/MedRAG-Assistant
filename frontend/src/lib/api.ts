/* Thin client over the FastAPI backend. All requests go through the same-origin
   /api/v1 proxy route, which forwards them to API_BASE_URL server-side. The JWT
   lives in localStorage; every helper reads it from there so pages stay simple. */
import { getSession } from "./session";

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

function authHeaders(): Record<string, string> {
  const token = getSession()?.token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function raiseForStatus(response: Response): Promise<void> {
  if (response.ok) return;
  let detail = `Request failed (${response.status})`;
  try {
    const body = await response.json();
    if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  } catch {
    // non-JSON error body; keep the generic message
  }
  throw new ApiError(response.status, detail);
}

export async function login(email: string, password: string) {
  const response = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: email, password }),
  });
  await raiseForStatus(response);
  return response.json();
}

export async function getJson(path: string, params?: Record<string, string>) {
  const query = params ? `?${new URLSearchParams(params)}` : "";
  const response = await fetch(`${path}${query}`, { headers: authHeaders() });
  await raiseForStatus(response);
  return response.json();
}

export async function postJson(path: string, payload: unknown) {
  const response = await fetch(path, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await raiseForStatus(response);
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

export async function patchJson(path: string, payload: unknown) {
  const response = await fetch(path, {
    method: "PATCH",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await raiseForStatus(response);
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

export async function del(path: string) {
  const response = await fetch(path, { method: "DELETE", headers: authHeaders() });
  await raiseForStatus(response);
}

export async function uploadDocument(
  fields: Record<string, string>,
  file: File,
  path = "/api/v1/documents",
) {
  const form = new FormData();
  for (const [key, value] of Object.entries(fields)) form.append(key, value);
  form.append("file", file);
  const response = await fetch(path, { method: "POST", headers: authHeaders(), body: form });
  await raiseForStatus(response);
  return response.json();
}

export type SseEvent = { event: string; data: string };

/** Yield {event, data} pairs from the backend SSE stream. */
export async function* chatStream(payload: unknown): AsyncGenerator<SseEvent> {
  const response = await fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await raiseForStatus(response);
  if (!response.body) throw new ApiError(0, "Streaming is not supported by this browser.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let event = "message";
  let dataLines: string[] = [];

  const flushLine = function* (line: string): Generator<SseEvent> {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).replace(/^ /, ""));
    } else if (line === "") {
      if (dataLines.length) yield { event, data: dataLines.join("\n") };
      event = "message";
      dataLines = [];
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";
    for (const line of lines) yield* flushLine(line);
  }
  for (const line of buffer.split(/\r?\n/)) yield* flushLine(line);
  yield* flushLine("");
}

export function apiErrorDetail(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Cannot reach the API server.";
}
