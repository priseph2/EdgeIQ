const BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "https://edgeiq-production-52f2.up.railway.app";

export interface Prediction {
  match_id: string;
  home_team: string;
  away_team: string;
  league: string;
  sport: string;
  start_time: string;
  home_prob: number;
  draw_prob: number | null;
  away_prob: number;
  confidence: "high" | "medium" | "low";
  pick: string;
  value_flag: boolean;
  best_home_odds: number | null;
  best_draw_odds: number | null;
  best_away_odds: number | null;
  model_version: string;
}

export interface ClaudeAnalysis {
  key_factors: string[];
  model_alignment: string;
  model_alignment_reason: string;
  confidence_narrative: string;
  main_risk: string;
  suggested_stake_pct: number;
  value_assessment: string;
  pick: string;
}

export interface Analytics {
  summary: {
    total_bets: number;
    total_staked: number;
    total_pnl: number;
    roi_pct: number;
    win_rate_pct: number;
    avg_odds: number;
    wins: number;
    losses: number;
  };
  by_sport: Record<string, { staked: number; pnl: number; bets: number; wins: number; roi: number }>;
  by_bookmaker: Record<string, { staked: number; pnl: number; bets: number; roi: number }>;
  by_tag: Record<string, { staked: number; pnl: number; bets: number }>;
}

export interface OddsRow {
  match_id: string;
  home_team: string;
  away_team: string;
  league: string;
  start_time: string;
  bookmaker: string;
  home_odds: number | null;
  draw_odds: number | null;
  away_odds: number | null;
}

export interface ValueBet {
  match_id: string;
  home_team: string;
  away_team: string;
  league: string;
  start_time: string;
  selection: string;
  edge_pct: number;
  model_prob: number;
  market_prob: number;
  best_odds: number;
  detected_at: string;
}

export interface ArbAlert {
  match_id: string;
  home_team: string;
  away_team: string;
  league: string;
  profit_pct: number;
  stakes_json: Record<string, { stake: number; book: string }>;
  detected_at: string;
}

export interface Bet {
  id: string;
  sport: string | null;
  league: string | null;
  selection: string;
  bookmaker: string;
  odds: number;
  stake: number;
  status: string;
  pnl: number | null;
  tag: string | null;
  notes: string | null;
  placed_at: string;
  settled_at: string | null;
}

export async function fetchTodayPredictions(sport?: string, date?: string): Promise<Prediction[]> {
  const params = new URLSearchParams();
  if (sport) params.set("sport", sport);
  if (date) params.set("date", date);
  const query = params.toString();
  const url = `${BASE}/predictions/today${query ? `?${query}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchAIAnalysis(matchId: string): Promise<ClaudeAnalysis> {
  const res = await fetch(`${BASE}/predictions/${matchId}/analysis`, { method: "POST", cache: "no-store" });
  if (!res.ok) throw new Error("AI analysis failed");
  return res.json();
}

export async function fetchModelStats() {
  const res = await fetch(`${BASE}/predictions/model/stats`, { cache: "no-store" });
  if (!res.ok) return {};
  return res.json();
}

export async function fetchAnalytics(): Promise<Analytics | null> {
  const res = await fetch(`${BASE}/bets/analytics`, { cache: "no-store" });
  if (!res.ok) return null;
  return res.json();
}

export async function fetchBets(): Promise<Bet[]> {
  const res = await fetch(`${BASE}/bets?limit=500`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export async function logBet(bet: {
  match_id?: string;
  sport?: string;
  league?: string;
  selection: string;
  bookmaker: string;
  odds: number;
  stake: number;
  tag?: string;
  notes?: string;
  confidence_stars?: number;
}) {
  const res = await fetch(`${BASE}/bets/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bet),
  });
  if (!res.ok) throw new Error("Failed to log bet");
  return res.json();
}

export async function fetchTodayOdds(): Promise<OddsRow[]> {
  const res = await fetch(`${BASE}/odds/today`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchValueBets(): Promise<ValueBet[]> {
  const res = await fetch(`${BASE}/odds/value-bets`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchArbAlerts(): Promise<ArbAlert[]> {
  const res = await fetch(`${BASE}/odds/arb`, { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}
