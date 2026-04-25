"use client";
import { useState } from "react";
import type { Prediction, ClaudeAnalysis } from "@/lib/api";
import { fetchAIAnalysis } from "@/lib/api";
import {
  cn, formatOdds, formatProb, confidenceColor,
  valueAssessmentColor, sportEmoji, formatKickoff,
} from "@/lib/utils";

interface Props {
  prediction: Prediction;
}

export default function PredictionCard({ prediction: p }: Props) {
  const [analysis, setAnalysis] = useState<ClaudeAnalysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchAIAnalysis(p.match_id);
      setAnalysis(result);
      setExpanded(true);
    } catch {
      setError("AI analysis failed. Check API key.");
    } finally {
      setLoading(false);
    }
  };

  const pickProb =
    p.pick === "home" ? p.home_prob :
    p.pick === "draw" ? (p.draw_prob ?? 0) :
    p.away_prob;

  return (
    <div className={cn(
      "rounded-xl border bg-[#0f172a] p-4 flex flex-col gap-3 transition-all",
      p.value_flag ? "border-emerald-500/40" : "border-slate-800"
    )}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs text-slate-500 mb-0.5">
            {sportEmoji(p.sport)} {p.league} · {formatKickoff(p.start_time)}
          </p>
          <p className="font-semibold text-white leading-tight">
            {p.home_team} <span className="text-slate-500">vs</span> {p.away_team}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className={cn("text-xs px-2 py-0.5 rounded-full border font-medium", confidenceColor(p.confidence))}>
            {p.confidence.toUpperCase()}
          </span>
          {p.value_flag && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 font-medium">
              VALUE BET
            </span>
          )}
        </div>
      </div>

      {/* Probability bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-slate-500 mb-1">
          <span>{p.home_team}</span>
          {p.draw_prob != null && <span>Draw</span>}
          <span>{p.away_team}</span>
        </div>
        <div className="flex h-2 rounded-full overflow-hidden gap-0.5">
          <div
            className={cn("h-full transition-all", p.pick === "home" ? "bg-indigo-500" : "bg-slate-700")}
            style={{ width: `${p.home_prob * 100}%` }}
          />
          {p.draw_prob != null && (
            <div
              className={cn("h-full transition-all", p.pick === "draw" ? "bg-indigo-500" : "bg-slate-700")}
              style={{ width: `${p.draw_prob * 100}%` }}
            />
          )}
          <div
            className={cn("h-full transition-all", p.pick === "away" ? "bg-indigo-500" : "bg-slate-700")}
            style={{ width: `${p.away_prob * 100}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-slate-400">
          <span>{formatProb(p.home_prob)}</span>
          {p.draw_prob != null && <span>{formatProb(p.draw_prob)}</span>}
          <span>{formatProb(p.away_prob)}</span>
        </div>
      </div>

      {/* Odds row */}
      {(p.best_home_odds || p.best_away_odds) && (
        <div className="flex gap-2 text-xs">
          {[
            { label: p.home_team, odds: p.best_home_odds, sel: "home" },
            ...(p.best_draw_odds ? [{ label: "Draw", odds: p.best_draw_odds, sel: "draw" }] : []),
            { label: p.away_team, odds: p.best_away_odds, sel: "away" },
          ].map((item) => (
            <div
              key={item.sel}
              className={cn(
                "flex-1 text-center rounded-lg py-1.5 border",
                item.sel === p.pick
                  ? "bg-indigo-600/20 border-indigo-500/40 text-indigo-300"
                  : "bg-slate-800 border-slate-700 text-slate-400"
              )}
            >
              <p className="truncate px-1">{item.label}</p>
              <p className="font-bold text-sm mt-0.5">{formatOdds(item.odds)}</p>
            </div>
          ))}
        </div>
      )}

      {/* xG / Total score line */}
      {(p.home_xg != null && p.away_xg != null) && (
        <div className="flex items-center justify-between text-xs text-slate-500 px-0.5">
          <span>xG</span>
          <span className="font-medium text-slate-300">
            {p.home_xg.toFixed(2)} <span className="text-slate-600">–</span> {p.away_xg.toFixed(2)}
          </span>
          <span>xG</span>
        </div>
      )}
      {p.predicted_total != null && (
        <div className="flex items-center justify-between text-xs text-slate-500 px-0.5">
          <span>Predicted total</span>
          <span className="font-medium text-slate-300">{p.predicted_total.toFixed(1)} pts</span>
        </div>
      )}

      {/* Pick summary */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-300">
          Pick: <span className="font-semibold text-white">{p.pick.toUpperCase()}</span>
          <span className="text-slate-500 ml-1">({formatProb(pickProb)})</span>
        </p>
        <button
          onClick={handleAnalyze}
          disabled={loading}
          className={cn(
            "text-xs px-3 py-1.5 rounded-lg font-medium transition-colors",
            loading
              ? "bg-slate-700 text-slate-500 cursor-wait"
              : "bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-400 border border-indigo-500/30"
          )}
        >
          {loading ? "Analysing…" : analysis ? "Re-analyse" : "AI Analysis"}
        </button>
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      {/* Claude Analysis Panel */}
      {analysis && expanded && (
        <div className="border-t border-slate-700 pt-3 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-indigo-400">Claude AI Analysis</p>
            <span className={cn("text-xs font-medium", valueAssessmentColor(analysis.value_assessment))}>
              {analysis.value_assessment.replace("_", " ").toUpperCase()}
            </span>
          </div>
          <p className="text-sm text-slate-300 leading-relaxed">{analysis.confidence_narrative}</p>
          <div className="space-y-1">
            {analysis.key_factors.map((f, i) => (
              <p key={i} className="text-xs text-slate-400 flex gap-1.5">
                <span className="text-indigo-500 mt-0.5">▸</span>{f}
              </p>
            ))}
          </div>
          <p className="text-xs text-red-400">
            <span className="font-medium">Risk:</span> {analysis.main_risk}
          </p>
          <div className="flex gap-3 text-xs text-slate-500">
            <span>Stake: <span className="text-slate-300">{analysis.suggested_stake_pct}% bankroll</span></span>
            <span>Model: <span className="text-slate-300">{analysis.model_alignment}</span></span>
          </div>
          <button
            onClick={() => setExpanded(false)}
            className="text-xs text-slate-600 hover:text-slate-400"
          >
            Collapse ↑
          </button>
        </div>
      )}

      {analysis && !expanded && (
        <button
          onClick={() => setExpanded(true)}
          className="text-xs text-indigo-500 hover:text-indigo-300"
        >
          Show analysis ↓
        </button>
      )}
    </div>
  );
}
