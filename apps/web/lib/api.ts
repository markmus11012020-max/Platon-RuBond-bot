import type {
  BondOverview,
  BlocklistEntry,
  ChatMessage,
  ChatResponse,
  ConfirmResponse,
  CreditEventEntry,
  FreelanceResponse,
  HealthResponse,
  Bot,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail || detail;
    } catch {
      // keep status text
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const api = {
  bots: () => request<Bot[]>("/api/bots"),
  health: () => request<HealthResponse>("/api/health"),
  bondOverview: () => request<BondOverview>("/api/bots/bond/overview"),
  bondChat: (message: string, history: ChatMessage[]) =>
    request<ChatResponse>("/api/bots/bond/chat", {
      method: "POST",
      body: JSON.stringify({ message, history }),
    }),
  confirmAction: (id: string) =>
    request<ConfirmResponse>(`/api/bots/bond/actions/${id}/confirm`, {
      method: "POST",
    }),
  freelanceOrders: () =>
    request<FreelanceResponse>("/api/bots/freelance/orders"),
  riskBlocklist: () => request<BlocklistEntry[]>("/api/risk/blocklist"),
  riskEvents: () => request<CreditEventEntry[]>("/api/risk/events"),
  addRiskBlocklist: (
    token: string,
    payload: {
      isin: string;
      reason: string;
      source: string;
      source_url?: string;
    },
  ) =>
    request<BlocklistEntry>("/api/risk/blocklist", {
      method: "POST",
      headers: { "X-Admin-Token": token },
      body: JSON.stringify(payload),
    }),
  deleteRiskBlocklist: (token: string, isin: string) =>
    request<{ removed: boolean }>(`/api/risk/blocklist/${isin}`, {
      method: "DELETE",
      headers: { "X-Admin-Token": token },
    }),
};
