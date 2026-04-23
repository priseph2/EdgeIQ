const BASE = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

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

export async function fetchTodayPredictions(sport?: string): Promise<Prediction[]> {
  const url = `${BASE}/predictions/today${sport ? `?sport=${sport}` : ""}`;
  const res = await fetch(url, { next: { revalidate: 3600 } });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchAIAnalysis(matchId: string): Promise<ClaudeAnalysis> {
  const res = await fetch(`${BASE}/predictions/${matchId}/analysis`, { method: "POST" });
  if (!res.ok) throw new Error("AI analysis failed");
  return res.json();
}

export async function fetchModelStats() {
  const res = await fetch(`${BASE}/predictions/model/stats`);
  if (!res.ok) return {};
  return res.json();
}

export async function fetchAnalytics(): Promise<Analytics | null> {
  const res = await fetch(`${BASE}/bets/analytics`);
  if (!res.ok) return null;
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
