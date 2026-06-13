import * as React from "react";

type Bar = { t: string; o: number; h: number; l: number; c: number };

const W = 480;
const H = 160;
const PAD = { top: 12, right: 12, bottom: 28, left: 44 };

function makeScale(bars: Bar[]) {
  if (bars.length === 0) return { min: 0, max: 1, range: 1 };
  const prices = bars.flatMap((b) => [b.l, b.h]);
  const rawMin = Math.min(...prices);
  const rawMax = Math.max(...prices);
  const pad = (rawMax - rawMin) * 0.08 || 1;
  return { min: rawMin - pad, max: rawMax + pad, range: rawMax - rawMin + 2 * pad };
}

function xOf(i: number, total: number) {
  const iw = W - PAD.left - PAD.right;
  return PAD.left + (iw / Math.max(total - 1, 1)) * i;
}

function yOf(price: number, scale: ReturnType<typeof makeScale>) {
  const ih = H - PAD.top - PAD.bottom;
  return PAD.top + ih * (1 - (price - scale.min) / scale.range);
}

function closePath(bars: Bar[], scale: ReturnType<typeof makeScale>) {
  if (bars.length === 0) return "";
  return bars
    .map((b, i) => {
      const x = xOf(i, bars.length);
      const y = yOf(b.c, scale);
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

function areaPath(bars: Bar[], scale: ReturnType<typeof makeScale>) {
  if (bars.length === 0) return "";
  const line = closePath(bars, scale);
  const lastX = xOf(bars.length - 1, bars.length).toFixed(1);
  const firstX = xOf(0, bars.length).toFixed(1);
  const baseY = (H - PAD.bottom).toFixed(1);
  return `${line} L ${lastX} ${baseY} H ${firstX} Z`;
}

function fmtPrice(v: number) {
  if (v >= 1000) return `$${(v / 1000).toFixed(2)}k`;
  return `$${v.toFixed(2)}`;
}

function closestBarIndex(bars: Bar[], date: string): number {
  if (!date || bars.length === 0) return -1;
  const target = new Date(date).getTime();
  let best = 0;
  let bestDiff = Infinity;
  bars.forEach((b, i) => {
    const diff = Math.abs(new Date(b.t).getTime() - target);
    if (diff < bestDiff) { bestDiff = diff; best = i; }
  });
  return best;
}

// Fallback SVG chart when API data is unavailable — shows entry → current price as a 2-point line
function FallbackChart({ entryPrice, markPrice, ticker }: { entryPrice: number; markPrice: number; ticker: string }) {
  const isUp = markPrice >= entryPrice;
  const lineColor = isUp ? "#34d399" : "#f87171";
  const pad = Math.abs(markPrice - entryPrice) * 0.2 || entryPrice * 0.02;
  const scaleMin = Math.min(entryPrice, markPrice) - pad;
  const scaleMax = Math.max(entryPrice, markPrice) + pad;
  const scaleRange = scaleMax - scaleMin;

  const yEntry = PAD.top + (H - PAD.top - PAD.bottom) * (1 - (entryPrice - scaleMin) / scaleRange);
  const yMark = PAD.top + (H - PAD.top - PAD.bottom) * (1 - (markPrice - scaleMin) / scaleRange);
  const xEntry = xOf(0, 2);
  const xMark = xOf(1, 2);
  const baseY = H - PAD.bottom;
  const gradId = `fg-${ticker}`;

  return (
    <div className="rounded-[8px] border border-[rgba(243,242,238,0.06)] bg-[rgba(243,242,238,0.02)] overflow-hidden">
      <div className="flex items-center justify-between px-3 pt-2.5 pb-1">
        <span className="text-[10px] font-mono font-bold text-[#F3F2EE] tracking-wider">{ticker}</span>
        <span className={`text-[10px] font-mono font-bold ${isUp ? "text-emerald-400" : "text-red-400"}`}>
          {fmtPrice(markPrice)}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" style={{ display: "block" }}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.18" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="0.01" />
          </linearGradient>
        </defs>
        {/* Y ticks */}
        {[entryPrice, markPrice].map((v) => {
          const y = PAD.top + (H - PAD.top - PAD.bottom) * (1 - (v - scaleMin) / scaleRange);
          return (
            <g key={v}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y}
                stroke="rgba(243,242,238,0.05)" strokeDasharray="4 4" />
              <text x={PAD.left - 4} y={y + 3.5} textAnchor="end" fontSize="8" fill="#8B8D91" fontFamily="monospace">
                {fmtPrice(v)}
              </text>
            </g>
          );
        })}
        {/* Entry price dashed line */}
        <line x1={PAD.left} x2={W - PAD.right} y1={yEntry} y2={yEntry}
          stroke="#E55A1C" strokeWidth="1" strokeDasharray="4 3" opacity="0.7" />
        {/* Area */}
        <path
          d={`M ${xEntry.toFixed(1)} ${yEntry.toFixed(1)} L ${xMark.toFixed(1)} ${yMark.toFixed(1)} L ${xMark.toFixed(1)} ${baseY} H ${xEntry.toFixed(1)} Z`}
          fill={`url(#${gradId})`}
        />
        {/* Line */}
        <path
          d={`M ${xEntry.toFixed(1)} ${yEntry.toFixed(1)} L ${xMark.toFixed(1)} ${yMark.toFixed(1)}`}
          fill="none" stroke={lineColor} strokeWidth="1.5" strokeLinecap="round"
        />
        {/* Entry dot */}
        <circle cx={xEntry} cy={yEntry} r="5" fill="#E55A1C" stroke="#0B0B0D" strokeWidth="2" />
        {/* Current dot */}
        <circle cx={xMark} cy={yMark} r="5" fill={lineColor} stroke="#0B0B0D" strokeWidth="2" />
        {/* X labels */}
        <text x={xEntry} y={H - 6} textAnchor="middle" fontSize="8" fill="#8B8D91" fontFamily="monospace">Entry</text>
        <text x={xMark} y={H - 6} textAnchor="middle" fontSize="8" fill="#8B8D91" fontFamily="monospace">Now</text>
      </svg>
    </div>
  );
}

interface EntryFill {
  price: number;
  date: string | null;
  shares?: number | null;
}

interface StockMiniChartProps {
  ticker: string;
  entryPrice: number | null;
  entryDate: string | null;
  markPrice?: number | null;
  period?: string;
  entries?: EntryFill[];
}

export function StockMiniChart({ ticker, entryPrice, entryDate, markPrice, period = "1M", entries }: StockMiniChartProps) {
  const [bars, setBars] = React.useState<Bar[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    fetch(`/api/stock-bars?ticker=${encodeURIComponent(ticker)}&period=${period}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => { if (!cancelled) { setBars(d.points ?? []); setLoading(false); } })
      .catch(() => { if (!cancelled) { setError(true); setLoading(false); } });
    return () => { cancelled = true; };
  }, [ticker, period]);

  if (loading) {
    return (
      <div className="h-[160px] rounded-[8px] bg-[rgba(243,242,238,0.03)] border border-[rgba(243,242,238,0.06)] flex items-center justify-center">
        <div className="w-4 h-4 rounded-full border-2 border-[#0b7bff] border-t-transparent animate-spin" />
      </div>
    );
  }

  // When API fails or returns no bars, show fallback 2-point chart if we have enough data
  if (error || bars.length === 0) {
    if (entryPrice != null && markPrice != null) {
      return <FallbackChart entryPrice={entryPrice} markPrice={markPrice} ticker={ticker} />;
    }
    return (
      <div className="h-[160px] rounded-[8px] bg-[rgba(243,242,238,0.03)] border border-[rgba(243,242,238,0.06)] flex items-center justify-center">
        <span className="text-[10px] font-mono text-[#8B8D91]">No market data</span>
      </div>
    );
  }

  const scale = makeScale(bars);
  const last = bars[bars.length - 1];
  const first = bars[0];
  const isUp = last.c >= first.c;
  const lineColor = isUp ? "#34d399" : "#f87171";
  const fillColor = isUp ? "#34d399" : "#f87171";

  // Build entry markers — one per fill if entries array provided, else single fallback
  const resolvedEntries: Array<{ x: number; y: number; isAdd: boolean }> = React.useMemo(() => {
    const fills = entries && entries.length > 0
      ? entries
      : entryPrice != null ? [{ price: entryPrice, date: entryDate, shares: null }] : [];
    return fills
      .map((e, i) => {
        const idx = e.date ? closestBarIndex(bars, e.date) : -1;
        if (idx < 0) return null;
        return { x: xOf(idx, bars.length), y: yOf(e.price, scale), isAdd: i > 0 };
      })
      .filter((m): m is NonNullable<typeof m> => m !== null);
  }, [bars, entries, entryPrice, entryDate, scale]);

  // Dashed horizontal line at VWAP entry price (entryPrice is already VWAP when entries provided)
  const entryY = entryPrice != null ? yOf(entryPrice, scale) : null;

  const yTicks = [scale.min + scale.range * 0.25, scale.min + scale.range * 0.5, scale.min + scale.range * 0.75].map(
    (v) => Math.round(v * 100) / 100
  );

  return (
    <div className="rounded-[8px] border border-[rgba(243,242,238,0.06)] bg-[rgba(243,242,238,0.02)] overflow-hidden">
      <div className="flex items-center justify-between px-3 pt-2.5 pb-1">
        <span className="text-[10px] font-mono font-bold text-[#F3F2EE] tracking-wider">{ticker}</span>
        <span className={`text-[10px] font-mono font-bold ${isUp ? "text-emerald-400" : "text-red-400"}`}>
          {fmtPrice(last.c)}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" style={{ display: "block" }}>
        <defs>
          <linearGradient id={`sg-${ticker}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={fillColor} stopOpacity="0.18" />
            <stop offset="100%" stopColor={fillColor} stopOpacity="0.01" />
          </linearGradient>
          <clipPath id={`clip-${ticker}`}>
            <rect x={PAD.left} y={PAD.top} width={W - PAD.left - PAD.right} height={H - PAD.top - PAD.bottom} />
          </clipPath>
        </defs>

        {/* Y ticks */}
        {yTicks.map((tick) => {
          const y = yOf(tick, scale);
          return (
            <g key={tick}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y}
                stroke="rgba(243,242,238,0.05)" strokeDasharray="4 4" />
              <text x={PAD.left - 4} y={y + 3.5} textAnchor="end" fontSize="8" fill="#8B8D91" fontFamily="monospace">
                {fmtPrice(tick)}
              </text>
            </g>
          );
        })}

        {/* Entry price horizontal line */}
        {entryPrice != null && entryY != null && (
          <line x1={PAD.left} x2={W - PAD.right} y1={entryY} y2={entryY}
            stroke="#E55A1C" strokeWidth="1" strokeDasharray="4 3" opacity="0.7" />
        )}

        {/* Area + line */}
        <g clipPath={`url(#clip-${ticker})`}>
          <path d={areaPath(bars, scale)} fill={`url(#sg-${ticker})`} />
          <path d={closePath(bars, scale)} fill="none" stroke={lineColor} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
        </g>

        {/* Entry point markers — one dot per fill */}
        {resolvedEntries.map((m, i) => (
          <g key={i}>
            {/* outer ring only on first entry; add-ons get a smaller ring */}
            <circle cx={m.x} cy={m.y} r={m.isAdd ? 7 : 9} fill="none"
              stroke="#E55A1C" strokeWidth="1" opacity={m.isAdd ? 0.25 : 0.4} />
            <circle cx={m.x} cy={m.y} r="5" fill="#E55A1C" stroke="#0B0B0D" strokeWidth="2" />
            {m.isAdd && (
              <text x={m.x} y={m.y - 12} textAnchor="middle" fontSize="7"
                fill="#E55A1C" fontFamily="monospace" opacity="0.8">+add</text>
            )}
          </g>
        ))}

        {/* X axis labels — first and last */}
        {bars.length > 0 && (() => {
          const fmtDate = (iso: string) => {
            const d = new Date(iso);
            return `${d.getMonth() + 1}/${d.getDate()}`;
          };
          return (
            <>
              <text x={xOf(0, bars.length)} y={H - 6} textAnchor="middle" fontSize="8" fill="#8B8D91" fontFamily="monospace">
                {fmtDate(bars[0].t)}
              </text>
              <text x={xOf(bars.length - 1, bars.length)} y={H - 6} textAnchor="middle" fontSize="8" fill="#8B8D91" fontFamily="monospace">
                {fmtDate(bars[bars.length - 1].t)}
              </text>
            </>
          );
        })()}
      </svg>
    </div>
  );
}
