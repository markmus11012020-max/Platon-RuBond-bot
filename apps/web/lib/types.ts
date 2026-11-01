export type Bot = {
  id: string;
  name: string;
  tagline: string;
  icon: string;
  status: "live" | "beta" | "soon";
  accent: string;
  features: string[];
};

export type PortfolioSummary = {
  total_value_rub: number;
  profit_rub: number;
  annual_coupon_rub: number;
  weighted_ytm_pct: number | null;
  weighted_duration_years: number | null;
  risk_level: string;
  risk_score: number;
  positions_count: number;
};

export type PositionCard = {
  isin: string;
  name: string;
  qty: number;
  value_rub: number;
  weight_pct: number;
  ytm_pct: number | null;
  duration_years: number | null;
  rating: string | null;
  current_price_pct: number | null;
  buy_price_pct: number | null;
  pnl_rub: number | null;
  annual_coupon_rub: number | null;
  next_coupon_date: string | null;
  maturity_date: string | null;
  offer_date: string | null;
};

export type AllocationSlice = {
  name: string;
  value_rub: number;
  share_pct: number;
  color: string;
};

export type EventCard = {
  date: string;
  kind: "coupon" | "offer" | "maturity";
  title: string;
  isin: string;
  days: number;
};

export type CandidateCard = {
  isin: string;
  name: string;
  ytm_pct: number;
  duration_years: number;
  rating: string;
  price_pct: number;
  volume_mn_rub: number;
  reason: string;
  risk_flags: string[];
};

export type ExcludedCandidate = {
  isin: string;
  name: string;
  reason: string;
  severity: "blocked" | "review";
};

export type BondOverview = {
  as_of: string;
  summary: PortfolioSummary;
  positions: PositionCard[];
  allocation: AllocationSlice[];
  rating_mix: Record<string, number>;
  events: EventCard[];
  candidates: CandidateCard[];
  excluded: ExcludedCandidate[];
  insights: string[];
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ActionLeg = {
  side: "buy" | "sell";
  isin: string;
  name: string;
  quantity: number;
  price_pct: number;
  amount_rub: number;
};

export type ActionCard = {
  id: string;
  title: string;
  description: string;
  kind: string;
  status: "proposed" | "confirmed" | "cancelled";
  expected_effect: Record<string, string | number>;
  legs: ActionLeg[];
  risk_notes: string[];
};

export type ChatResponse = {
  message: string;
  suggestions: string[];
  action: ActionCard | null;
};

export type ConfirmResponse = {
  action_id: string;
  status: string;
  message: string;
  audit_id: string;
  executed_at: string;
};

export type FreelanceOrder = {
  id: number;
  title: string;
  source: string;
  budget_text: string;
  score: number;
  url: string;
  published_at: string | null;
  category: string;
  matched_keywords: string[];
  red_flags: string[];
};

export type FreelanceResponse = {
  orders: FreelanceOrder[];
  summary: {
    count: number;
    top_score: number;
    source: string;
  };
};

export type HealthResponse = {
  status: string;
  service: string;
  environment: string;
  demo_mode: boolean;
  mcp_enabled: boolean;
  mcp_ready: boolean;
  mcp_mode: string;
  bonds_db: boolean;
  freelance_db: boolean;
};
