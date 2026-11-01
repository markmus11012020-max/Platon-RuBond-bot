import type {
  BondOverview,
  BlocklistEntry,
  ChatMessage,
  ChatResponse,
  ChatSessionResponse,
  ConfirmResponse,
  CreditEventEntry,
  FreelanceResponse,
  FundamentalsEntry,
  FundamentalsImportResult,
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
  bondChat: (message: string, history: ChatMessage[], sessionId?: string | null) =>
    request<ChatResponse>("/api/bots/bond/chat", {
      method: "POST",
      body: JSON.stringify({ message, history, session_id: sessionId || null }),
    }),
  createChatSession: () =>
    request<ChatSessionResponse>("/api/chat/session", { method: "POST" }),
  getChatSession: (sessionId: string) =>
    request<ChatSessionResponse>(`/api/chat/session/${sessionId}`),
  deleteChatSession: (sessionId: string) =>
    request<{ removed: boolean }>(`/api/chat/session/${sessionId}`, {
      method: "DELETE",
    }),
  confirmAction: (id: string) =>
    request<ConfirmResponse>(`/api/bots/bond/actions/${id}/confirm`, {
      method: "POST",
    }),
  freelanceOrders: () =>
    request<FreelanceResponse>("/api/bots/freelance/orders"),
  riskBlocklist: () => request<BlocklistEntry[]>("/api/risk/blocklist"),
  checkAdmin: (token: string) =>
    request<{ ok: boolean }>("/api/risk/check", {
      headers: { "X-Admin-Token": token },
    }),
  riskEvents: () => request<CreditEventEntry[]>("/api/risk/events"),
  riskFundamentals: (isin?: string, issuer?: string) => {
    const params = new URLSearchParams();
    if (isin) params.set("isin", isin);
    if (issuer) params.set("issuer", issuer);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request<FundamentalsEntry[]>(`/api/fundamentals${suffix}`);
  },
  addRiskFundamentals: (
    token: string,
    payload: {
      isin?: string;
      issuer?: string;
      period: string;
      revenue_rub?: number | null;
      net_profit_rub?: number | null;
      ebitda_rub?: number | null;
      net_debt_rub?: number | null;
      equity_rub?: number | null;
      current_ratio?: number | null;
      source: string;
      source_url?: string;
      notes?: string;
    },
  ) =>
    request<FundamentalsEntry>("/api/fundamentals", {
      method: "POST",
      headers: { "X-Admin-Token": token },
      body: JSON.stringify(payload),
    }),
  importRiskFundamentals: async (token: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(`${API_BASE}/api/fundamentals/import`, {
      method: "POST",
      headers: { "X-Admin-Token": token },
      body: form,
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
    return (await response.json()) as FundamentalsImportResult;
  },
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
