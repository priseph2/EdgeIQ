import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatOdds(odds: number | null | undefined): string {
  if (!odds) return "–";
  return odds.toFixed(2);
}

export function formatProb(prob: number | null | undefined): string {
  if (prob == null) return "–";
  return `${(prob * 100).toFixed(1)}%`;
}

export function formatPnl(pnl: number): string {
  const sign = pnl >= 0 ? "+" : "";
  return `${sign}£${pnl.toFixed(2)}`;
}

export function confidenceColor(confidence: string): string {
  switch (confidence) {
    case "high":   return "text-emerald-400 bg-emerald-400/10 border-emerald-400/20";
    case "medium": return "text-yellow-400 bg-yellow-400/10 border-yellow-400/20";
    case "low":    return "text-slate-400 bg-slate-400/10 border-slate-400/20";
    default:       return "text-slate-400 bg-slate-400/10 border-slate-400/20";
  }
}

export function valueAssessmentColor(va: string): string {
  switch (va) {
    case "strong_value":   return "text-emerald-400";
    case "moderate_value": return "text-yellow-400";
    case "fair":           return "text-slate-400";
    case "avoid":          return "text-red-400";
    default:               return "text-slate-400";
  }
}

export function sportEmoji(sport: string): string {
  return sport === "basketball" ? "🏀" : "⚽";
}

export function formatKickoff(isoString: string): string {
  const d = new Date(isoString);
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Africa/Lagos" });
}

export function formatDate(isoString: string): string {
  const d = new Date(isoString);
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "Africa/Lagos" });
}
