"use client";

export default function DashboardError({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="rounded-xl border border-red-500/20 bg-[#0f172a] p-8 text-center space-y-3">
      <p className="text-red-400 font-medium">Could not load predictions</p>
      <p className="text-slate-500 text-sm">The backend may be starting up or temporarily unavailable.</p>
      <button
        onClick={reset}
        className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-medium transition-colors"
      >
        Try again
      </button>
    </div>
  );
}
