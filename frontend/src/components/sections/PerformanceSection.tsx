import { useMemo, useState } from "react";
import ChartAreaStep from "@/components/ui/chart-area-step";
import { AnimateNumber } from "@/components/ui/animated-blur-number";
import type { EquityPosition } from "@/types";
import { cn } from "@/lib/utils";

type TimeRange = "1D" | "1W" | "1M" | "6M" | "1Y" | "All";
const RANGES: TimeRange[] = ["1D", "1W", "1M", "6M", "1Y", "All"];
const DAYS_BACK: Record<TimeRange, number> = {
  "1D": 1, "1W": 7, "1M": 30, "6M": 180, "1Y": 365, "All": 730,
};

interface PerformanceSectionProps {
  positions: EquityPosition[];
}

function buildChartData(positions: EquityPosition[], range: TimeRange) {
  const today = new Date();
  today.setHours(23, 59, 59, 0);

  const daysBack = DAYS_BACK[range];
  const startDate = new Date(today);
  startDate.setDate(startDate.getDate() - daysBack);
  startDate.setHours(0, 0, 0, 0);

  if (range === "All") {
    for (const p of positions) {
      if (!p.opened_at) continue;
      const d = new Date(p.opened_at);
      if (d < startDate) { startDate.setTime(d.getTime()); startDate.setHours(0,0,0,0); }
    }
  }

  const days: Date[] = [];
  const cursor = new Date(startDate);
  while (cursor <= today) {
    days.push(new Date(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }

  const nowTs = today.getTime();

  const todayDate = new Date(today);
  todayDate.setHours(0, 0, 0, 0);

  return days.map((day) => {
    const dayTs = day.getTime();
    const isToday = day.toDateString() === todayDate.toDateString();
    let cumPnl = 0;

    for (const pos of positions) {
      const openTs = pos.opened_at
        ? new Date(pos.opened_at).setHours(0, 0, 0, 0)
        : nowTs - 7 * 86400_000;
      if (dayTs < openTs) continue;
      // always use fraction=1 for today so current P&L is exact
      const fraction = isToday
        ? 1
        : Math.min((dayTs - openTs) / Math.max(nowTs - openTs, 1), 1);
      cumPnl += ((pos.unrealized_pnl ?? 0) + (pos.realized_pnl ?? 0)) * fraction;
    }

    const mm = String(day.getMonth() + 1).padStart(2, "0");
    const dd = String(day.getDate()).padStart(2, "0");
    return { label: `${mm}/${dd}`, value: parseFloat(cumPnl.toFixed(2)) };
  });
}

export function PerformanceSection({ positions }: PerformanceSectionProps) {
  const [range, setRange] = useState<TimeRange>("1W");

  const chartData = useMemo(() => buildChartData(positions, range), [positions, range]);

  const openPositions = positions.filter((p) => p.status === "open");
  const totalUnrealized = openPositions.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0);
  const totalNotional = positions
    .filter((p) => p.entry_price != null && p.shares != null)
    .reduce((s, p) => s + p.entry_price! * p.shares!, 0);

  const confPositions = positions.filter((p) => p.confidence != null);
  const avgConfidence =
    confPositions.length > 0
      ? confPositions.reduce((s, p) => s + p.confidence!, 0) / confPositions.length
      : null;

  type StatCard = {
    value: number; label: string; positive: boolean | null;
    prefix?: string; suffix?: string; decimals?: number;
  };

  const statCards: StatCard[] = [
    { value: positions.length, label: "Total positions", positive: null },
    { value: openPositions.length, label: "Open", positive: openPositions.length > 0 },
    ...(totalNotional > 0
      ? [{ value: totalNotional, label: "Notional deployed", positive: null, prefix: "$", decimals: 2 }]
      : []),
    ...(avgConfidence != null
      ? [{ value: Math.round(avgConfidence * 1000) / 10, label: "Avg confidence", positive: avgConfidence > 0.5, suffix: "%", decimals: 1 }]
      : []),
  ];

  const pnlPositive = totalUnrealized >= 0;

  return (
    <section id="performance" className="py-24 px-6 bg-[#0B0B0D]">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-12">
          <p className="text-[10px] font-mono tracking-widest uppercase text-[#0b7bff] mb-3">
            Alpaca Paper Trading
          </p>
          <h2 className="text-4xl font-black text-[#F3F2EE]" style={{ fontFamily: "Poppins, sans-serif" }}>
            Portfolio Performance
          </h2>
        </div>

        {/* Big unrealized P&L */}
        <div className="mb-10 rounded-[16px] border border-[rgba(243,242,238,0.07)] bg-[#1A1A1E] p-8 flex flex-col gap-1">
          <p className="text-[10px] font-mono tracking-widest uppercase text-[#8B8D91] mb-3">
            Unrealized P&amp;L
          </p>
          <div className={cn(pnlPositive ? "text-emerald-400" : "text-red-400")}>
            <AnimateNumber
              value={Math.abs(totalUnrealized)}
              prefix={totalUnrealized < 0 ? "-$" : "+$"}
              format={{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
              className="text-6xl font-semibold tracking-tight"
              duration={600}
            />
          </div>
          {totalNotional > 0 && (
            <p className="text-[#8B8D91] text-sm font-mono mt-2">
              on ${totalNotional.toFixed(2)} notional deployed
            </p>
          )}
        </div>

        {/* Stat cards */}
        {statCards.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-10">
            {statCards.map((s) => (
              <div key={s.label} className="rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] p-5">
                <div
                  className={cn(
                    "text-2xl font-black mb-1",
                    s.positive === true ? "text-emerald-400" : s.positive === false ? "text-red-400" : "text-[#F3F2EE]"
                  )}
                  style={{ fontFamily: "Poppins, sans-serif" }}
                >
                  <AnimateNumber
                    value={Math.abs(s.decimals != null ? s.value : Math.round(s.value))}
                    prefix={s.prefix ? (s.value < 0 ? `-${s.prefix}` : s.prefix) : undefined}
                    suffix={s.suffix}
                    format={s.decimals != null ? { minimumFractionDigits: s.decimals, maximumFractionDigits: s.decimals } : undefined}
                    className="text-2xl font-black"
                  />
                </div>
                <span className="text-xs text-[#8B8D91] font-mono uppercase tracking-wider">{s.label}</span>
              </div>
            ))}
          </div>
        )}

        {/* Chart with time filters */}
        <div className="w-full rounded-none border-[3px] border-[rgba(243,242,238,0.12)] bg-[#0B0B0D] p-4 text-[#F3F2EE] shadow-[4px_4px_0_0_#0b7bff]">
          <div className="mb-4 flex items-center justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-widest text-[#8B8D91] font-mono">Portfolio P&amp;L</p>
              <h3 className="mt-1 text-sm font-bold font-mono">Cumulative unrealized + realized</h3>
            </div>
            {/* Time range filters */}
            <div className="flex items-center gap-1 bg-[rgba(243,242,238,0.04)] rounded-[6px] p-1">
              {RANGES.map((r) => (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  className={cn(
                    "px-2.5 py-1 rounded-[4px] text-[10px] font-mono transition-all",
                    r === range
                      ? "bg-[#0b7bff] text-white"
                      : "text-[#8B8D91] hover:text-[#F3F2EE] hover:bg-[rgba(243,242,238,0.06)]"
                  )}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>
          <ChartAreaStep data={chartData} />
        </div>
      </div>
    </section>
  );
}
