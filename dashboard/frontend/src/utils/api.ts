export type Provider = "ollama";

type JsonValue = null | boolean | number | string | JsonValue[] | { [k: string]: JsonValue };

export type ActionCommand = {
  kind: string;
  payload: Record<string, JsonValue>;
};

export class ApiError extends Error {
  readonly url: string;
  readonly status: number;
  readonly statusText: string;
  readonly responseBody: unknown;

  constructor(args: { message: string; url: string; status: number; statusText: string; responseBody: unknown }) {
    super(args.message);
    this.name = "ApiError";
    this.url = args.url;
    this.status = args.status;
    this.statusText = args.statusText;
    this.responseBody = args.responseBody;
  }
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function tryExtractErrorMessageFromJson(v: unknown): string | null {
  if (typeof v === "string") return v.trim() || null;
  if (!isPlainObject(v)) return null;

  const candidates = [v.error, v.message, v.detail, v.title, v.reason];
  for (const c of candidates) {
    if (typeof c === "string" && c.trim()) return c.trim();
  }

  if (isPlainObject(v.detail)) {
    const nested = tryExtractErrorMessageFromJson(v.detail);
    if (nested) return nested;
  }

  return null;
}

function tryExtractErrorCode(v: unknown): string | null {
  if (!isPlainObject(v)) return null;

  const direct = typeof v.error === "string" && v.error.trim() ? v.error.trim() : null;
  if (direct) return direct;

  if (isPlainObject(v.detail)) {
    const nested = tryExtractErrorCode(v.detail);
    if (nested) return nested;
  }

  return null;
}

export function describeRobotErrorCode(code: string | null | undefined): string | null {
  const value = String(code || "").trim().toLowerCase();
  if (!value) return null;

  if (value === "unauthorized") return "غير مصرح. سجّل الدخول بالـ PIN أولًا.";
  if (value === "invalid_pin") return "PIN غير صحيح.";
  if (value === "pin_not_configured") return "PIN غير مُعدّ على الهوست.";
  if (value === "rate_limited") return "محاولات كثيرة. انتظر قليلًا ثم أعد المحاولة.";
  if (value === "state_manager_unavailable") return "مدير حالة الروبوت غير متاح حاليًا.";
  if (value === "command_queue_unavailable") return "قناة أوامر الروبوت غير متاحة.";
  if (value === "service_degraded") return "بعض خدمات الهوست غير جاهزة حاليًا.";
  if (value === "invalid_new_pin") return "الـ PIN الجديد غير صالح.";
  return null;
}

async function readResponseBody(r: Response): Promise<{ text: string; json: unknown | null }> {
  const text = await r.text().catch(() => "");
  const contentType = r.headers.get("content-type") || "";
  const looksJson = contentType.includes("application/json") || /^\s*[[{]/.test(text);
  if (!looksJson || !text.trim()) return { text, json: null };
  try {
    return { text, json: JSON.parse(text) as JsonValue };
  } catch {
    return { text, json: null };
  }
}

function validateRelativeOrHttpUrl(input: string, label = "URL"): string {
  const raw = String(input ?? "").trim();
  if (!raw) throw new Error(`${label}: الرابط فارغ.`);
  if (/\s/.test(raw)) throw new Error(`${label}: الرابط يحتوي على مسافات.`);

  if (raw.startsWith("/")) return raw;

  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    throw new Error(`${label}: رابط غير صالح.`);
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") throw new Error(`${label}: لازم يبدأ بـ http أو https.`);
  return u.toString();
}

export function validateHttpUrl(input: string, label = "الرابط"): string {
  const raw = String(input ?? "").trim();
  if (!raw) throw new Error(`${label}: الرابط فارغ.`);
  if (/\s/.test(raw)) throw new Error(`${label}: الرابط يحتوي على مسافات.`);

  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    throw new Error(`${label}: رابط غير صالح.`);
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") throw new Error(`${label}: لازم يبدأ بـ http أو https.`);
  return u.toString();
}

export function validateOllamaBaseUrl(input: string, label = "عنوان Ollama"): string {
  const raw = validateHttpUrl(input, label);
  const u = new URL(raw);

  // Common cleanup: remove specific endpoints if user pasted full API URL
  const path = u.pathname.replace(/\/$/, "");
  if (path.endsWith("/api/generate") || path.endsWith("/api/tags") || path.endsWith("/api/chat") || path.endsWith("/api/version")) {
    const newPath = path.replace(/\/api\/(generate|tags|chat|version)$/, "");
    u.pathname = newPath;
  }

  // Ensure no trailing slash
  if (u.pathname.endsWith("/")) {
    u.pathname = u.pathname.slice(0, -1);
  }

  const host = u.hostname.toLowerCase();
  const isLocal = host === "localhost" || host === "127.0.0.1" || host === "::1";
  if (isLocal) return u.toString();

  if (host.endsWith(".local")) return u.toString();

  const m = host.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (m) {
    const nums = m.slice(1).map((x) => Number(x));
    if (nums.every((n) => Number.isInteger(n) && n >= 0 && n <= 255)) {
      const [a, b] = nums as [number, number, number, number];
      const isPrivate =
        a === 10 ||
        (a === 172 && b >= 16 && b <= 31) ||
        (a === 192 && b === 168) ||
        (a === 169 && b === 254);
      if (isPrivate) return u.toString();
    }
  }

  const whitelistRaw = localStorage.getItem("local-robot-tester:ollamaWhitelist") || "";
  const whitelist = whitelistRaw
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
  if (whitelist.includes(u.origin) || whitelist.includes(u.toString().replace(/\/$/, ""))) return u.toString();

  throw new Error(`${label}: العنوان غير مسموح به. أضفه للـWhitelist في localStorage.`);
}

export function validateModelName(input: string, label = "اسم الموديل"): string {
  const raw = String(input ?? "").trim();
  if (!raw) throw new Error(`${label}: مطلوب.`);
  if (raw.length > 200) throw new Error(`${label}: طويل جدًا.`);
  if (/\s/.test(raw)) throw new Error(`${label}: لا يجب أن يحتوي على مسافات.`);
  if (!/^[A-Za-z0-9][A-Za-z0-9._/@:-]*$/.test(raw)) throw new Error(`${label}: يحتوي على أحرف غير مسموحة.`);
  return raw;
}

export function getRobotSessionFromStorage(): { token: string; expiresAtMs: number } | null {
  try {
    const token = sessionStorage.getItem("local-robot-tester:robot-session") || "";
    const expRaw = sessionStorage.getItem("local-robot-tester:robot-session-exp") || "";
    const expiresAtMs = Number(expRaw);
    if (!token || !Number.isFinite(expiresAtMs)) return null;
    if (Date.now() >= expiresAtMs) {
      clearRobotSessionFromStorage();
      return null;
    }
    return { token, expiresAtMs };
  } catch {
    return null;
  }
}

export function clearRobotSessionFromStorage(): void {
  try {
    sessionStorage.removeItem("local-robot-tester:robot-session");
    sessionStorage.removeItem("local-robot-tester:robot-session-exp");
  } catch {
    return;
  }
}

export function getRobotAuthHeaders(): Record<string, string> {
  const s = getRobotSessionFromStorage();
  if (!s) return {};
  return { "x-robot-session": s.token };
}

type RobotAuthRequestDetail = { reason?: string | null };
type RobotAuthResultDetail = { ok: boolean };

let authRequestPromise: Promise<boolean> | null = null;

export function requestRobotAuth(reason?: string | null): Promise<boolean> {
  if (typeof window === "undefined") return Promise.resolve(false);
  if (authRequestPromise) return authRequestPromise;

  authRequestPromise = new Promise<boolean>((resolve) => {
    const onResult = (ev: Event) => {
      const e = ev as CustomEvent<RobotAuthResultDetail>;
      authRequestPromise = null;
      resolve(Boolean(e.detail?.ok));
    };
    window.addEventListener("robot-auth:result", onResult, { once: true });
    window.dispatchEvent(new CustomEvent<RobotAuthRequestDetail>("robot-auth:request", { detail: { reason: reason ?? null } }));
  });

  return authRequestPromise;
}

function normalizeHeaders(input: HeadersInit | undefined): Record<string, string> {
  if (!input) return {};
  if (input instanceof Headers) return Object.fromEntries(input.entries());
  if (Array.isArray(input)) return Object.fromEntries(input);
  return { ...input };
}

async function fetchJson<T>(
  urlInput: string,
  init?: RequestInit,
): Promise<T> {
  const url = validateRelativeOrHttpUrl(urlInput, "عنوان الطلب");

  for (let attempt = 0; attempt < 2; attempt++) {
    const initHeaders = normalizeHeaders(init?.headers);
    const authHeaders = getRobotAuthHeaders();
    const headers: Record<string, string> = { ...initHeaders, ...authHeaders };
    const finalInit: RequestInit = { ...init, headers, credentials: init?.credentials ?? "include" };

    let r: Response;
    try {
      r = await fetch(url, finalInit);
    } catch (e) {
      const msg = String(e);
      throw new Error(`تعذر الاتصال بالسيرفر: ${msg}`);
    }

    const { text, json } = await readResponseBody(r);

    if (r.ok) {
      if (json === null) {
        const contentType = r.headers.get("content-type") || "";
        const snippet = text.trim().slice(0, 200);
        const parts = [contentType ? `content-type=${contentType}` : null, snippet ? `body=${snippet}` : null].filter(
          Boolean,
        );
        const details = parts.length ? ` (${parts.join(" | ")})` : "";
        throw new Error(`تعذر قراءة استجابة JSON من السيرفر.${details}`);
      }
      return json as T;
    }

    const serverError = tryExtractErrorCode(json);

    const shouldPromptAuth = serverError === "unauthorized" || serverError === "pin_not_configured";
    if (r.status === 401 && attempt === 0 && shouldPromptAuth) {
      const ok = await requestRobotAuth(serverError);
      if (ok) continue;
    }

    let extracted = describeRobotErrorCode(serverError) || tryExtractErrorMessageFromJson(json) || (text.trim() ? text.trim() : null);
    if (r.status === 401 && !extracted && serverError) {
      extracted = describeRobotErrorCode(serverError);
    }
    const suffix = extracted ? `: ${extracted}` : "";
    throw new ApiError({
      message: `فشل الطلب (${r.status}${r.statusText ? ` ${r.statusText}` : ""})${suffix}`,
      url,
      status: r.status,
      statusText: r.statusText,
      responseBody: json ?? text,
    });
  }

  throw new Error("فشل المصادقة.");
}

export async function postJson<T>(
  url: string,
  body: unknown,
  extraHeaders?: Record<string, string>,
): Promise<T> {
  return await fetchJson<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(extraHeaders || {}) },
    body: JSON.stringify(body),
  });
}

export async function putJson<T>(
  url: string,
  body: unknown,
  extraHeaders?: Record<string, string>,
): Promise<T> {
  return await fetchJson<T>(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...(extraHeaders || {}) },
    body: JSON.stringify(body),
  });
}

export async function getJson<T>(url: string): Promise<T> {
  return await fetchJson<T>(url);
}

export async function logoutRobotSession(): Promise<void> {
  const session = getRobotSessionFromStorage();
  try {
    await postJson<{ success: boolean }>("/api/settings/logout", {}, session ? { "x-robot-session": session.token } : undefined);
  } catch {
    // Local session is the source of truth for client-side auth continuity.
  } finally {
    clearRobotSessionFromStorage();
  }
}
