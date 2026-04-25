export default function DashboardLoading() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Header skeleton */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-7 w-52 bg-slate-800 rounded-lg" />
          <div className="h-4 w-40 bg-slate-800/60 rounded" />
        </div>
        <div className="flex gap-3">
          <div className="h-8 w-28 bg-slate-800 rounded-lg" />
          <div className="h-8 w-32 bg-slate-800 rounded-lg" />
        </div>
      </div>

      {/* Model stats skeleton */}
      <div className="flex gap-4">
        <div className="h-8 w-56 bg-slate-800 rounded-lg" />
        <div className="h-8 w-56 bg-slate-800 rounded-lg" />
      </div>

      {/* Cards skeleton */}
      <div className="space-y-2">
        <div className="h-4 w-24 bg-slate-800 rounded" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="rounded-xl border border-slate-800 bg-[#0f172a] p-4 space-y-3">
              <div className="h-3 w-28 bg-slate-800 rounded" />
              <div className="h-5 w-full bg-slate-800 rounded" />
              <div className="h-2 w-full bg-slate-800 rounded-full" />
              <div className="h-8 w-full bg-slate-800 rounded-lg" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
