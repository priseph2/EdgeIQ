"use client";
import { useState, useEffect } from "react";
import { fetchAnalytics, fetchBets, logBet } from "@/lib/api";
import type { Analytics, Bet } from "@/lib/api";
import { formatPnl, cn } from "@/lib/utils";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from "recharts";

interface ChartPoint { date: string; pnl: number }

function buildBankrollCurve(bets: Bet[]): ChartPoint[] {
  const settled = bets
    .filter((b) => b.settled_at && b.pnl != null)
    .sort((a, b) => new Date(a.settled_at!).getTime() - new Date(b.settled_at!).getTime());
  let running = 0;
  return settled.map((b) => {
    running += b.pnl!;
    return {
      date: new Date(b.settled_at!).toLocaleDateString("en-NG", { month: "short", day: "numeric" }),
      pnl: Math.round(running * 100) / 100,
    };
  });
}

export default function TrackerPage() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [chartData, setChartData] = useState<ChartPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    selection: "", bookmaker: "", odds: "", stake: "", sport: "", tag: "", notes: "",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    Promise.all([fetchAnalytics(), fetchBets()]).then(([a, bets]) => {
      setAnalytics(a);
      setChartData(buildBankrollCurve(bets));
      setLoading(false);
    });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await logBet({
        selection: form.selection,
        bookmaker: form.bookmaker,
        odds: parseFloat(form.odds),
        stake: parseFloat(form.stake),
        sport: form.sport || undefined,
        tag: form.tag || undefined,
        notes: form.notes || undefined,
      });
      setSaved(true);
      setShowForm(false);
      setForm({ selection: "", bookmaker: "", odds: "", stake: "", sport: "", tag: "", notes: "" });
      const [updated, bets] = await Promise.all([fetchAnalytics(), fetchBets()]);
      setAnalytics(updated);
      setChartData(buildBankrollCurve(bets));
      setTimeout(() => setSaved(false), 3000);
    } catch {
      alert("Failed to save bet");
    } finally {
      setSaving(false);
    }
  };

  const summary = analytics?.summary;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Bet Tracker</h1>
          <p className="text-sm text-slate-500 mt-0.5">P&L analytics and performance breakdown</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium transition-colors"
        >
          + Log Bet
        </button>
      </div>

      {saved && (
        <div className="px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm">
          Bet logged successfully
        </div>
      )}

      {/* Log bet form */}
      {showForm && (
        <form onSubmit={handleSubmit} className="rounded-xl border border-slate-700 bg-[#0f172a] p-4 space-y-3">
          <h2 className="text-sm font-semibold text-white">New Bet</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {[
              { key: "selection", label: "Selection (e.g. Home Win)", required: true },
              { key: "bookmaker", label: "Bookmaker", required: true },
              { key: "odds", label: "Decimal Odds", required: true, type: "number", step: "0.01", min: "1.01" },
              { key: "stake", label: "Stake (₦ or £)", required: true, type: "number", step: "0.01", min: "0" },
              { key: "sport", label: "Sport (optional)" },
              { key: "tag", label: "Tag (value/arb/gut)" },
            ].map((f) => (
              <div key={f.key} className="flex flex-col gap-1">
                <label className="text-xs text-slate-500">{f.label}</label>
                <input
                  type={f.type || "text"}
                  step={f.step}
                  min={f.min}
                  required={f.required}
                  value={(form as Record<string, string>)[f.key]}
                  onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
                  className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                />
              </div>
            ))}
          </div>
          <div className="flex gap-1">
            <input
              type="text"
              placeholder="Notes (optional)"
              value={form.notes}
              onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))}
              className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
            />
          </div>
          <div className="flex gap-2 justify-end">
            <button type="button" onClick={() => setShowForm(false)}
              className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">Cancel</button>
            <button type="submit" disabled={saving}
              className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium disabled:opacity-50">
              {saving ? "Saving…" : "Save Bet"}
            </button>
          </div>
        </form>
      )}

      {loading && (
        <div className="text-slate-500 text-sm">Loading analytics…</div>
      )}

      {!loading && !summary && (
        <div className="rounded-xl border border-slate-800 bg-[#0f172a] p-8 text-center">
          <p className="text-slate-400 text-sm">No settled bets yet.</p>
          <p className="text-slate-600 text-xs mt-1">Log your first bet above to start tracking P&L.</p>
        </div>
      )}

      {summary && (
        <>
          {/* Summary cards */}
          <div className="grid gap-4 grid-cols-2 sm:grid-cols-4">
            {[
              { label: "Total P&L", value: formatPnl(summary.total_pnl), color: summary.total_pnl >= 0 ? "text-emerald-400" : "text-red-400" },
              { label: "ROI", value: `${summary.roi_pct.toFixed(2)}%`, color: summary.roi_pct >= 0 ? "text-emerald-400" : "text-red-400" },
              { label: "Win Rate", value: `${summary.win_rate_pct.toFixed(1)}%`, color: "text-white" },
              { label: "Total Bets", value: `${summary.total_bets}`, color: "text-white" },
            ].map((card) => (
              <div key={card.label} className="rounded-xl bg-[#0f172a] border border-slate-800 p-4">
                <p className="text-xs text-slate-500 mb-1">{card.label}</p>
                <p className={cn("text-xl font-bold", card.color)}>{card.value}</p>
              </div>
            ))}
          </div>

          {/* Bankroll curve */}
          {chartData.length >= 2 && (
            <div className="rounded-xl bg-[#0f172a] border border-slate-800 p-4">
              <h3 className="text-sm font-semibold text-slate-300 mb-4">Cumulative P&L</h3>
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} width={40} />
                  <Tooltip
                    contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, fontSize: 12 }}
                    labelStyle={{ color: "#94a3b8" }}
                    itemStyle={{ color: "#818cf8" }}
                    formatter={(v) => [formatPnl(Number(v)), "P&L"]}
                  />
                  <Area
                    type="monotone"
                    dataKey="pnl"
                    stroke="#6366f1"
                    strokeWidth={2}
                    fill="url(#pnlGrad)"
                    dot={false}
                    activeDot={{ r: 4, fill: "#6366f1" }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Breakdown tables */}
          <div className="grid gap-4 sm:grid-cols-2">
            {/* By sport */}
            <div className="rounded-xl bg-[#0f172a] border border-slate-800 p-4">
              <h3 className="text-sm font-semibold text-slate-300 mb-3">By Sport</h3>
              <table className="w-full text-xs">
                <thead><tr className="text-slate-500 border-b border-slate-800">
                  <th className="text-left pb-1.5">Sport</th>
                  <th className="text-right pb-1.5">Bets</th>
                  <th className="text-right pb-1.5">P&L</th>
                  <th className="text-right pb-1.5">ROI</th>
                </tr></thead>
                <tbody>
                  {Object.entries(analytics!.by_sport).map(([sport, s]) => (
                    <tr key={sport} className="border-b border-slate-800/50">
                      <td className="py-1.5 capitalize text-slate-300">{sport}</td>
                      <td className="text-right text-slate-400">{s.bets}</td>
                      <td className={cn("text-right", s.pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {formatPnl(s.pnl)}
                      </td>
                      <td className={cn("text-right", s.roi >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {s.roi.toFixed(1)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* By bookmaker */}
            <div className="rounded-xl bg-[#0f172a] border border-slate-800 p-4">
              <h3 className="text-sm font-semibold text-slate-300 mb-3">By Bookmaker</h3>
              <table className="w-full text-xs">
                <thead><tr className="text-slate-500 border-b border-slate-800">
                  <th className="text-left pb-1.5">Bookmaker</th>
                  <th className="text-right pb-1.5">Bets</th>
                  <th className="text-right pb-1.5">P&L</th>
                  <th className="text-right pb-1.5">ROI</th>
                </tr></thead>
                <tbody>
                  {Object.entries(analytics!.by_bookmaker).map(([bk, s]) => (
                    <tr key={bk} className="border-b border-slate-800/50">
                      <td className="py-1.5 text-slate-300">{bk}</td>
                      <td className="text-right text-slate-400">{s.bets}</td>
                      <td className={cn("text-right", s.pnl >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {formatPnl(s.pnl)}
                      </td>
                      <td className={cn("text-right", s.roi >= 0 ? "text-emerald-400" : "text-red-400")}>
                        {s.roi.toFixed(1)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Export */}
          <div className="flex justify-end">
            <a
              href={`${process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"}/bets/export/csv`}
              className="text-sm text-indigo-400 hover:text-indigo-300 underline"
            >
              Export all bets (CSV)
            </a>
          </div>
        </>
      )}
    </div>
  );
}
