"use client";
import { useState, useEffect } from "react";
import { fetchTodayPredictions } from "@/lib/api";
import type { Prediction } from "@/lib/api";
import PredictionCard from "@/components/PredictionCard";
import { formatDate } from "@/lib/utils";

const LEAGUES_BY_SPORT: Record<string, string[]> = {
  all:        ["All", "NBA", "EuroLeague", "EuroCup", "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1"],
  basketball: ["All", "NBA", "EuroLeague", "EuroCup"],
  football:   ["All", "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1"],
};

function toLocalDateString(date: Date): string {
  // Format as YYYY-MM-DD in local time (avoids UTC-offset issues)
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

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
  const today = toLocalDateString(new Date());
  const [date, setDate] = useState(today);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [sport, setSport] = useState("all");
  const [league, setLeague] = useState("All");
  const [valueOnly, setValueOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    setLoading(true);
    setError(false);
    fetchTodayPredictions(sport === "all" ? undefined : sport, date)
      .then((p) => { setPredictions(p); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [sport, date, retryCount]);

  const handleSportChange = (s: string) => {
    setSport(s);
    if (!LEAGUES_BY_SPORT[s].includes(league)) setLeague("All");
  };

  const shiftDate = (days: number) => {
    const d = new Date(date + "T00:00:00");
    d.setDate(d.getDate() + days);
    setDate(toLocalDateString(d));
  };

  const isToday = date === today;
  const displayDate = date === today
    ? "Today"
    : formatDate(date + "T12:00:00");

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
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Predictions</h1>
          <p className="text-sm text-slate-500 mt-0.5">Match predictions across all covered leagues</p>
        </div>

        {/* Date navigator */}
        <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded-lg p-1">
          <button
            onClick={() => shiftDate(-1)}
            className="px-2 py-1 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition-colors text-sm"
            aria-label="Previous day"
          >
            ‹
          </button>
          <label className="relative cursor-pointer">
            <input
              type="date"
              value={date}
              onChange={(e) => e.target.value && setDate(e.target.value)}
              className="absolute inset-0 opacity-0 cursor-pointer w-full"
            />
            <span className={`px-3 py-1 text-sm font-medium select-none ${isToday ? "text-indigo-400" : "text-slate-200"}`}>
              {displayDate}
            </span>
          </label>
          <button
            onClick={() => shiftDate(1)}
            className="px-2 py-1 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition-colors text-sm"
            aria-label="Next day"
          >
            ›
          </button>
          {!isToday && (
            <button
              onClick={() => setDate(today)}
              className="px-2 py-1 rounded text-xs text-indigo-400 hover:text-indigo-300 transition-colors border-l border-slate-800 ml-1 pl-2"
            >
              Today
            </button>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
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

        <select
          value={league}
          onChange={(e) => setLeague(e.target.value)}
          className="bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
        >
          {LEAGUES_BY_SPORT[sport].map((l) => <option key={l} value={l}>{l}</option>)}
        </select>

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
            onClick={() => setRetryCount((c) => c + 1)}
            className="mt-3 px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && filtered.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-8 text-center">
          <p className="text-slate-500 text-sm">No predictions for {displayDate}.</p>
          {valueOnly
            ? <p className="text-slate-600 text-xs mt-1">No value bets detected — try removing the filter.</p>
            : <p className="text-slate-600 text-xs mt-1">Fixtures may not be loaded yet for this date.</p>
          }
        </div>
      )}

      {/* Results */}
      {!loading && !error && filtered.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((p) => <PredictionCard key={p.match_id} prediction={p} />)}
        </div>
      )}
    </div>
  );
}
