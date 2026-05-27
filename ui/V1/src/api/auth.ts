import { ApiError, apiRequest, getAccessToken, setAccessToken } from "./client";

const DEV_USERNAME = "xiagent-ui";
const DEV_PASSWORD = "secret-123";

interface AuthResponse {
  access_token: string;
  token_type: string;
}

async function login(): Promise<string> {
  const result = await apiRequest<AuthResponse>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: DEV_USERNAME, password: DEV_PASSWORD }),
  });
  setAccessToken(result.access_token);
  return result.access_token;
}

async function register(): Promise<void> {
  await apiRequest("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: DEV_USERNAME, password: DEV_PASSWORD }),
  });
}

export async function ensureAccessToken(): Promise<string> {
  const existingToken = getAccessToken();
  if (existingToken) return existingToken;

  try {
    return await login();
  } catch (error) {
    if (!(error instanceof ApiError)) throw error;
    await register();
    return login();
  }
}
