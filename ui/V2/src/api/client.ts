export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const TOKEN_KEY = "xiagent.v2.access_token";

let accessToken: string | null = loadToken();

export function setAccessToken(token: string | null): void {
  accessToken = token;
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function clearAccessToken(): void {
  setAccessToken(null);
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers({
    Accept: "application/json",
    ...init.headers,
  });
  if (accessToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  const response = await fetch(path, { ...init, headers });
  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();

  if (!response.ok) {
    throw new ApiError(readableErrorMessage(body, response.status), response.status, body);
  }

  return body as T;
}

function readableErrorMessage(body: unknown, status: number): string {
  const serverMessage = extractServerMessage(body);
  if (serverMessage && !isTransportMessage(serverMessage)) return serverMessage;

  if (status === 400) return "请求内容有误，请检查后重试。";
  if (status === 401) return "登录状态已失效，请重新登录。";
  if (status === 403) return "当前账号没有权限执行这个操作。";
  if (status === 404) return "没有找到对应的数据。";
  if (status === 405) return "当前服务暂时不支持这个操作，请刷新后重试。";
  if (status === 409) return "当前操作与已有数据冲突，请刷新后重试。";
  if (status === 422) return "提交内容不完整，请检查必填项。";
  if (status >= 500) return "服务处理失败，请稍后重试。";

  return `请求失败，状态码 ${status}`;
}

function extractServerMessage(body: unknown): string | null {
  if (typeof body === "object" && body !== null) {
    const maybeError = body as { error?: { message?: unknown }; detail?: unknown; message?: unknown };
    if (typeof maybeError.error?.message === "string") return maybeError.error.message;
    if (typeof maybeError.message === "string") return maybeError.message;
    if (typeof maybeError.detail === "string") return maybeError.detail;
  }
  return null;
}

function isTransportMessage(message: string): boolean {
  return [
    "Method Not Allowed",
    "Not Found",
    "Internal Server Error",
    "Unauthorized",
    "Forbidden",
    "Access token is missing or invalid",
  ].includes(message);
}

function loadToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}
