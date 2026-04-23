"use client";
import { useState, useEffect } from "react";
import { fetchTodayPredictions } from "@/lib/api";
import type { Prediction } from "@/lib/api";
import PredictionCard from "@/components/PredictionCard";
import { sportEmoji } from "@/lib/utils";

const LEAGUES = ["All", "NBA", "EuroLeague", "Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1"];
const SPORTS = ["all", "basketball", "football"];

export default function PredictionsPage() {
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [sport, setSport] = useState("all");
  const [league, setLeague] = useState("All");
  const [valueOnly, setValueOnly] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchTodayPredictions(sport === "all" ? undefined : sport)
      .then((p) => { setPredictions(p); setLoading(false); });
  }, [sport]);

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
        <div className="flex gap-1 bg-slate-900 rounded-lg p-1 border border-slate-800">
          {SPORTS.map((s) => (
            <button
              key={s}
              onClick={() => setSport(s)}
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
          {LEAGUES.map((l) => <option key={l} value={l}>{l}</option>)}
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
          {loading ? "Loading…" : `${filtered.length} matches`}
        </span>
      </div>

      {!loading && filtered.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-8 text-center">
          <p className="text-slate-500 text-sm">No predictions match your filters.</p>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {filtered.map((p) => <PredictionCard key={p.match_id} prediction={p} />)}
      </div>
    </div>
  );
}
