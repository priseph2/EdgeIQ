"use client";
import { useState, useEffect } from "react";
import { fetchTodayPredictions } from "@/lib/api";
import type { Prediction } from "@/lib/api";
import PredictionCard from "@/components/PredictionCard";

const LEAGUES_BY_SPORT: Record<string, string[]> = {
  all:        ["All", "NBA", "EuroLeague", "EuroCup", "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1"],
  basketball: ["All", "NBA", "EuroLeague", "EuroCup"],
  football:   ["All", "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1"],
};

function CardSkeleton() {
  return (
    <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-4 space-y-3 animate-pulse">
      <div className="h-3 w-28 bg-slate-800 rounded" />
      <div className="h-5 w-full bg-slate-800 rounded" />
      <div className="h-2 w-full bg-slate-800 rounded-full" />
      <div className="flex gap-2">
        <div className="flex-1 h-10 bg-slate-800 rounded-lg" />
        <div className="flex-1 h-10 bg-slate-800 rounded-lg" />
      </div>
    </div>
  );
}

export default function PredictionsPage() {
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [sport, setSport] = useState("all");
  const [league, setLeague] = useState("All");
  const [valueOnly, setValueOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    fetchTodayPredictions(sport === "all" ? undefined : sport)
      .then((p) => { setPredictions(p); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [sport]);

  // Reset league when sport changes if current league doesn't belong to new sport
  const handleSportChange = (s: string) => {
    setSport(s);
    if (!LEAGUES_BY_SPORT[s].includes(league)) setLeague("All");
  };

  const filtered = predictions
    .filter((p) => league === "All" || p.league === league)
    .filter((p) => !valueOnly || p.value_flag)
    .sort((a, b) => {
      if (a.value_flag && !b.value_flag) return -1;
      if (!a.value_flag && b.value_flag) return 1;
      const order: Record<string, number> = { high: 0, medium: 1, low: 2 };
      return (order[a.confidence] ?? 2) - (order[b.confidence] ?? 2);
    });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Predictions</h1>
        <p className="text-sm text-slate-500 mt-0.5">Today&apos;s match predictions across all covered leagues</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        {/* Sport toggle */}
        <div className="flex gap-1 bg-slate-900 rounded-lg p-1 border border-slate-800">
          {(["all", "basketball", "football"] as const).map((s) => (
            <button
              key={s}
              onClick={() => handleSportChange(s)}
              className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${
                sport === s ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {s === "all" ? "All Sports" : s === "basketball" ? "🏀 Basketball" : "⚽ Football"}
            </button>
          ))}
        </div>

        {/* League dropdown — only shows leagues for the selected sport */}
        <select
          value={league}
          onChange={(e) => setLeague(e.target.value)}
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
        >
          {LEAGUES_BY_SPORT[sport].map((l) => <option key={l} value={l}>{l}</option>)}
        </select>

        {/* Value bets toggle */}
        <button
          onClick={() => setValueOnly(!valueOnly)}
          className={`px-3 py-1.5 text-xs rounded-lg border font-medium transition-colors ${
            valueOnly
              ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-400"
              : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
          }`}
        >
          Value bets only
        </button>

        <span className="text-xs text-slate-500 ml-auto">
          {loading ? "Loading…" : error ? "Error" : `${filtered.length} matches`}
        </span>
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[...Array(6)].map((_, i) => <CardSkeleton key={i} />)}
        </div>
      )}

      {/* Error state */}
      {!loading && error && (
        <div className="rounded-xl border border-red-500/20 bg-[#0f172a] p-8 text-center">
          <p className="text-red-400 text-sm">Failed to load predictions.</p>
          <p className="text-slate-600 text-xs mt-1">The backend may be starting up — try again in a moment.</p>
          <button
            onClick={() => handleSportChange(sport)}
            className="mt-3 px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && filtered.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-8 text-center">
          <p className="text-slate-500 text-sm">No predictions match your filters.</p>
          {valueOnly && (
            <p className="text-slate-600 text-xs mt-1">No value bets detected today — try removing the filter.</p>
          )}
        </div>
      )}

      {/* Results */}
      {!loading && !error && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((p) => <PredictionCard key={p.match_id} prediction={p} />)}
        </div>
      )}
    </div>
  );
}
