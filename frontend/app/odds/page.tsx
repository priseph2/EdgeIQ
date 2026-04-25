"use client";
import { useState, useEffect, useCallback } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { fetchValueBets, fetchTodayOdds, fetchArbAlerts } from "@/lib/api";
import type { ValueBet, OddsRow, ArbAlert } from "@/lib/api";
import { cn, formatOdds, formatKickoff } from "@/lib/utils";

interface MatchGroup {
  match_id: string;
  home_team: string;
  away_team: string;
  league: string;
  start_time: string;
  bookmakers: { bookmaker: string; home_odds: number | null; draw_odds: number | null; away_odds: number | null }[];
}

function groupByMatch(rows: OddsRow[]): MatchGroup[] {
  const map: Record<string, MatchGroup> = {};
  for (const row of rows) {
    if (!map[row.match_id]) {
      map[row.match_id] = {
        match_id: row.match_id,
        home_team: row.home_team,
        away_team: row.away_team,
        league: row.league,
        start_time: row.start_time,
        bookmakers: [],
      };
    }
    map[row.match_id].bookmakers.push({
      bookmaker: row.bookmaker,
      home_odds: row.home_odds,
      draw_odds: row.draw_odds,
      away_odds: row.away_odds,
    });
  }
  return Object.values(map).sort((a, b) => a.start_time.localeCompare(b.start_time));
}

function best(vals: (number | null)[]): number {
  return Math.max(...vals.map((v) => v ?? 0));
}

export default function OddsPage() {
  const [valueBets, setValueBets] = useState<ValueBet[]>([]);
  const [oddsRows, setOddsRows] = useState<OddsRow[]>([]);
  const [arbAlerts, setArbAlerts] = useState<ArbAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const [vb, odds, arb] = await Promise.all([
      fetchValueBets(),
      fetchTodayOdds(),
      fetchArbAlerts(),
    ]);
    setValueBets(vb);
    setOddsRows(odds);
    setArbAlerts(arb);
    setLastRefresh(new Date());
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const matchGroups = groupByMatch(oddsRows);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Odds & Alerts</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Live odds comparison, value bets, and arbitrage opportunities
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-xs text-slate-600">
              Updated {lastRefresh.toLocaleTimeString("en-NG", { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 text-xs font-medium transition-colors disabled:opacity-50"
          >
            {loading ? "Refreshing…" : "↻ Refresh"}
          </button>
        </div>
      </div>

      <Tabs.Root defaultValue="value-bets" className="space-y-4">
        <Tabs.List className="flex gap-1 bg-slate-900 rounded-lg p-1 border border-slate-800 w-fit">
          {[
            { value: "value-bets", label: `Value Bets${valueBets.length ? ` (${valueBets.length})` : ""}` },
            { value: "odds", label: `Odds${matchGroups.length ? ` (${matchGroups.length})` : ""}` },
            { value: "arb", label: `Arb Alerts${arbAlerts.length ? ` (${arbAlerts.length})` : ""}` },
          ].map((tab) => (
            <Tabs.Trigger
              key={tab.value}
              value={tab.value}
              className={cn(
                "px-4 py-1.5 text-xs font-medium rounded-md transition-colors",
                "text-slate-400 hover:text-slate-200",
                "data-[state=active]:bg-indigo-600 data-[state=active]:text-white"
              )}
            >
              {tab.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        {/* VALUE BETS TAB */}
        <Tabs.Content value="value-bets" className="space-y-3">
          {!loading && valueBets.length === 0 && (
            <EmptyState message="No value bets detected today." sub="Value bets appear when model probability exceeds market implied probability by 5%+" />
          )}
          {valueBets.map((vb) => (
            <div
              key={`${vb.match_id}-${vb.selection}`}
              className="rounded-xl border border-emerald-500/30 bg-[#0f172a] p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs text-slate-500 mb-0.5">{vb.league} · {formatKickoff(vb.start_time)}</p>
                  <p className="font-semibold text-white">{vb.home_team} <span className="text-slate-500">vs</span> {vb.away_team}</p>
                  <p className="text-sm text-slate-400 mt-1">
                    Selection: <span className="text-white font-medium capitalize">{vb.selection}</span>
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-2xl font-bold text-emerald-400">+{vb.edge_pct.toFixed(1)}%</p>
                  <p className="text-xs text-slate-500">edge</p>
                </div>
              </div>
              <div className="mt-3 flex gap-4 text-xs">
                <div className="flex-1 bg-slate-800/60 rounded-lg p-2 text-center">
                  <p className="text-slate-500 mb-0.5">Model prob</p>
                  <p className="text-white font-semibold">{(vb.model_prob * 100).toFixed(1)}%</p>
                </div>
                <div className="flex-1 bg-slate-800/60 rounded-lg p-2 text-center">
                  <p className="text-slate-500 mb-0.5">Market implied</p>
                  <p className="text-white font-semibold">{(vb.market_prob * 100).toFixed(1)}%</p>
                </div>
                <div className="flex-1 bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-2 text-center">
                  <p className="text-slate-500 mb-0.5">Best odds</p>
                  <p className="text-emerald-400 font-bold">{formatOdds(vb.best_odds)}</p>
                </div>
              </div>
            </div>
          ))}
        </Tabs.Content>

        {/* ODDS COMPARISON TAB */}
        <Tabs.Content value="odds" className="space-y-4">
          {!loading && matchGroups.length === 0 && (
            <EmptyState message="No odds available for today." sub="Trigger odds ingestion to pull latest lines." />
          )}
          {matchGroups.map((group) => {
            const hasDraw = group.bookmakers.some((b) => b.draw_odds != null);
            const bestHome = best(group.bookmakers.map((b) => b.home_odds));
            const bestDraw = best(group.bookmakers.map((b) => b.draw_odds));
            const bestAway = best(group.bookmakers.map((b) => b.away_odds));
            return (
              <div key={group.match_id} className="rounded-xl border border-slate-800 bg-[#0f172a] overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between">
                  <div>
                    <p className="text-xs text-slate-500 mb-0.5">{group.league} · {formatKickoff(group.start_time)}</p>
                    <p className="font-semibold text-white text-sm">{group.home_team} <span className="text-slate-500">vs</span> {group.away_team}</p>
                  </div>
                  <span className="text-xs text-slate-600">{group.bookmakers.length} books</span>
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-500 border-b border-slate-800/50">
                      <th className="text-left px-4 py-2">Bookmaker</th>
                      <th className="text-center px-3 py-2">Home</th>
                      {hasDraw && <th className="text-center px-3 py-2">Draw</th>}
                      <th className="text-center px-3 py-2">Away</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.bookmakers
                      .sort((a, b) => (b.home_odds ?? 0) - (a.home_odds ?? 0))
                      .map((bm) => (
                        <tr key={bm.bookmaker} className="border-b border-slate-800/30 hover:bg-slate-800/20">
                          <td className="px-4 py-2 text-slate-300 capitalize">{bm.bookmaker}</td>
                          <td className={cn("text-center px-3 py-2 font-medium", bm.home_odds === bestHome && bestHome > 0 ? "text-emerald-400" : "text-slate-400")}>
                            {formatOdds(bm.home_odds)}
                          </td>
                          {hasDraw && (
                            <td className={cn("text-center px-3 py-2 font-medium", bm.draw_odds === bestDraw && bestDraw > 0 ? "text-emerald-400" : "text-slate-400")}>
                              {formatOdds(bm.draw_odds)}
                            </td>
                          )}
                          <td className={cn("text-center px-3 py-2 font-medium", bm.away_odds === bestAway && bestAway > 0 ? "text-emerald-400" : "text-slate-400")}>
                            {formatOdds(bm.away_odds)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </Tabs.Content>

        {/* ARB ALERTS TAB */}
        <Tabs.Content value="arb" className="space-y-3">
          {!loading && arbAlerts.length === 0 && (
            <EmptyState message="No arbitrage opportunities today." sub="Arb alerts appear when combined back-all stakes across bookmakers yield guaranteed profit." />
          )}
          {arbAlerts.map((arb, i) => (
            <div key={i} className="rounded-xl border border-yellow-500/30 bg-[#0f172a] p-4">
              <div className="flex items-start justify-between gap-3 mb-3">
                <div>
                  <p className="text-xs text-slate-500 mb-0.5">{arb.league}</p>
                  <p className="font-semibold text-white">{arb.home_team} <span className="text-slate-500">vs</span> {arb.away_team}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-2xl font-bold text-yellow-400">+{arb.profit_pct.toFixed(2)}%</p>
                  <p className="text-xs text-slate-500">guaranteed profit</p>
                </div>
              </div>
              <div className="flex gap-2 flex-wrap">
                {Object.entries(arb.stakes_json).map(([side, info]) => (
                  <div key={side} className="bg-slate-800/60 rounded-lg px-3 py-2 text-xs">
                    <p className="text-slate-500 capitalize mb-0.5">{side}</p>
                    <p className="text-white font-medium">₦{info.stake.toLocaleString()}</p>
                    <p className="text-slate-400">{info.book}</p>
                  </div>
                ))}
              </div>
              <p className="text-xs text-slate-600 mt-2">
                Detected {new Date(arb.detected_at).toLocaleTimeString("en-NG", { hour: "2-digit", minute: "2-digit" })}
              </p>
            </div>
          ))}
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}

function EmptyState({ message, sub }: { message: string; sub: string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-8 text-center">
      <p className="text-slate-400 text-sm">{message}</p>
      <p className="text-slate-600 text-xs mt-1">{sub}</p>
    </div>
  );
}
