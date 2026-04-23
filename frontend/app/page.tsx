import { fetchTodayPredictions, fetchModelStats } from "@/lib/api";
import PredictionCard from "@/components/PredictionCard";
import { formatDate } from "@/lib/utils";

export const revalidate = 3600;

export default async function DashboardPage() {
  const [predictions, modelStats] = await Promise.all([
    fetchTodayPredictions(),
    fetchModelStats(),
  ]);

  const today = formatDate(new Date().toISOString());
  const valueBets = predictions.filter((p) => p.value_flag);
  const highConf = predictions.filter((p) => p.confidence === "high");

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Today&apos;s Intelligence</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {today} · {predictions.length} matches analysed
          </p>
        </div>
        <div className="flex gap-3 text-sm">
          {valueBets.length > 0 && (
            <div className="px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              {valueBets.length} value bet{valueBets.length !== 1 ? "s" : ""}
            </div>
          )}
          {highConf.length > 0 && (
            <div className="px-3 py-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              {highConf.length} high confidence
            </div>
          )}
        </div>
      </div>

      {/* Model stats strip */}
      {Object.keys(modelStats).length > 0 && (
        <div className="flex gap-4 flex-wrap">
          {Object.entries(modelStats).map(([sport, stats]: [string, unknown]) => {
            const s = stats as { accuracy?: number; brier_score?: number };
            return (
              <div
                key={sport}
                className="flex items-center gap-3 px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-400"
              >
                <span className="font-medium text-slate-200 capitalize">{sport}</span>
                <span>
                  Accuracy{" "}
                  <span className="text-white">
                    {((s.accuracy ?? 0) * 100).toFixed(1)}%
                  </span>
                </span>
                <span>
                  Brier{" "}
                  <span className="text-white">{(s.brier_score ?? 0).toFixed(3)}</span>
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Empty state */}
      {predictions.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-8 text-center">
          <p className="text-slate-400 text-sm">No predictions available yet.</p>
          <p className="text-slate-600 text-xs mt-1">
            Run data ingestion and model training first.
          </p>
          <code className="block mt-3 text-xs text-indigo-400 bg-slate-900 rounded p-2">
            cd backend && python -m data.ingest_nba && python -m ml.train --sport all
          </code>
        </div>
      )}

      {/* Value bets pinned to top */}
      {valueBets.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-emerald-400 mb-3 uppercase tracking-wider">
            Value Bets
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {valueBets.map((p) => (
              <PredictionCard key={p.match_id} prediction={p} />
            ))}
          </div>
        </section>
      )}

      {/* All other predictions */}
      {predictions.filter((p) => !p.value_flag).length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-slate-500 mb-3 uppercase tracking-wider">
            All Predictions
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {predictions
              .filter((p) => !p.value_flag)
              .sort((a, b) => {
                const order: Record<string, number> = { high: 0, medium: 1, low: 2 };
                return (order[a.confidence] ?? 2) - (order[b.confidence] ?? 2);
              })
              .map((p) => (
                <PredictionCard key={p.match_id} prediction={p} />
              ))}
          </div>
        </section>
      )}
    </div>
  );
}
