import { apiRequest, setAccessToken } from "./client";
import type { AuthResponse, UserRecord } from "./types";

export async function login(username: string, password: string): Promise<AuthResponse> {
  const result = await apiRequest<AuthResponse>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  setAccessToken(result.access_token);
  return result;
}

export async function register(username: string, password: string): Promise<UserRecord> {
  return apiRequest<UserRecord>("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export async function getCurrentUser(): Promise<UserRecord> {
  return apiRequest<UserRecord>("/api/auth/me");
}
