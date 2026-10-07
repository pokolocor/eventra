export const money = (value: number, dp = 2): string =>
  (value < 0 ? "-$" : "$") +
  Math.abs(Number(value) || 0).toLocaleString("en-US", {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  });

export const compact = (value: number): string => {
  const n = Math.abs(Number(value) || 0);
  if (n >= 1e9) return (Number(value) / 1e9).toFixed(2) + "B";
  if (n >= 1e6) return (Number(value) / 1e6).toFixed(2) + "M";
  if (n >= 1e3) return (Number(value) / 1e3).toFixed(1) + "K";
  return String(Math.round(n));
};

export const pct = (value: number, dp = 2): string =>
  (Number(value) >= 0 ? "+" : "") + Number(value).toFixed(dp) + "%";

export const num = (value: number, dp = 4): string =>
  Number(value || 0).toLocaleString("en-US", { maximumFractionDigits: dp });

export const signed = (value: number): "pos" | "neg" | "neu" =>
  Number(value) > 0 ? "pos" : Number(value) < 0 ? "neg" : "neu";

export function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (!then) return "";
  const secs = Math.max(0, (Date.now() - then) / 1000);
  if (secs < 60) return `${Math.floor(secs)}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

export const clock = (iso: string): string =>
  new Date(iso).toLocaleTimeString("en-GB", { hour12: false });

export const human = (value: string): string => value.replace(/_/g, " ");
