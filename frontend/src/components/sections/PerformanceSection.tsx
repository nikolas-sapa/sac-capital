import { useMemo, useState } from "react";
import ChartAreaSmooth from "@/components/ui/chart-area-smooth";
import { AnimateNumber } from "@/components/ui/animated-blur-number";
import type { EquityPosition } from "@/types";
import { cn } from "@/lib/utils";

type TimeRange = "1D" | "1W" | "1M" | "6M" | "1Y" | "All";

const RANGES: TimeRange[] = ["1D", "1W", "1M", "6M", "1Y", "All"];

const DAYS_BACK: Record<TimeRange, number> = {
  "1D": 1,
  "1W": 7,
  "1M": 30,
  "6M": 180,
  "1Y": 365,
  "All": 730,
};

interface PerformanceSectionProps {
  positions: EquityPosition[];
}

function buildCumulativePnl(positions: EquityPosition[], range: TimeRange) {
  const today = new Date();
  today.setHours(23, 59, 59, 0);

  const daysBack = DAYS_BACK[range];
  const start = new Date(today);
  start.setDate(start.getDate() - daysBack);
  start.setHours(0, 0, 0, 0);

  // For "All": find earliest open date and use that as start
  let earliest = start;
  if (range === "All") {
    for (const p of positions) {
      if (!p.opened_at) continue;
      const d = new Date(p.opened_at);
      if (d < earliest) earliest = d;
    }
    earliest.setHours(0, 0, 0, 0);
  }

  const startDate = range === "All" ? earliest : start;

  // Build day array
  const days: Date[] = [];
  const cursor = new Date(startDate);
  while (cursor <= today) {
    days.push(new Date(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }

  // For each day compute cumulative P&L via linear interpolation
  const nowTs = today.getTime();

  return days.map((day) => {
    const dayTs = day.getTime();
    let cumPnl = 0;

    for (const pos of positions) {
      if (!pos.opened_at) continue;
      const openTs = new Date(pos.opened_at).setHours(0, 0, 0, 0);
      if (dayTs < openTs) continue;

      const totalMs = nowTs - openTs;
      const elapsedMs = dayTs - openTs;
      const fraction = totalMs > 0 ? Math.min(elapsedMs / totalMs, 1) : 1;
      const currentPnl = (pos.unrealized_pnl ?? 0) + (pos.realized_pnl ?? 0);
      cumPnl += currentPnl * fraction;
    }

    const month = String(day.getMonth() + 1).padStart(2, "0");
    const dd = String(day.getDate()).padStart(2, "0");
    const label =
      range === "6M" || range === "1Y" || range === "All"
        ? `${month}/${dd}`
        : `${month}/${dd}`;

    return { label, value: parseFloat(cumPnl.toFixed(2)) };
  });
}

export function PerformanceSection({ positions }: PerformanceSectionProps) {
  const [range, setRange] = useState<TimeRange>("1W");

  const chartData = useMemo(
    () => buildCumulativePnl(positions, range),
    [positions, range]
  );

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

  const totalPnl = positions.reduce(
    (s, p) => s + (p.unrealized_pnl ?? 0) + (p.realized_pnl ?? 0),
    0
  );
  const pnlPositive = totalPnl >= 0;

  type StatCard = {
    value: number;
    label: string;
    positive: boolean | null;
    prefix?: string;
    suffix?: string;
    decimals?: number;
  };

  const statCards: StatCard[] = [
    { value: positions.length, label: "Total positions", positive: null },
    { value: openPositions.length, label: "Open", positive: openPositions.length > 0 },
    ...(totalNotional > 0
      ? [{ value: totalNotional, label: "Notional deployed", positive: null, prefix: "$", decimals: 2 }]
      : []),
    ...(avgConfidence != null
      ? [
          {
            value: Math.round(avgConfidence * 1000) / 10,
            label: "Avg confidence",
            positive: avgConfidence > 0.5,
            suffix: "%",
            decimals: 1,
          },
        ]
      : []),
  ];

  return (
    <section id="performance" className="py-24 px-6 bg-[#0B0B0D]">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-12">
          <p className="text-[10px] font-mono tracking-widest uppercase text-[#0b7bff] mb-3">
            Alpaca Paper Trading
          </p>
          <h2
            className="text-4xl font-black text-[#F3F2EE]"
            style={{ fontFamily: "Poppins, sans-serif" }}
          >
            Portfolio Performance
          </h2>
        </div>

        {/* P&L hero + chart */}
        <div className="mb-10 rounded-[16px] border border-[rgba(243,242,238,0.07)] bg-[#1A1A1E] p-8">
          {/* Top row: P&L + time filters */}
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-8">
            <div>
              <p className="text-[10px] font-mono tracking-widest uppercase text-[#8B8D91] mb-2">
                Cumulative P&amp;L
              </p>
              <div className={cn(pnlPositive ? "text-[#0b7bff]" : "text-red-400")}>
                <AnimateNumber
                  value={Math.abs(totalPnl)}
                  prefix={totalPnl < 0 ? "-$" : "+$"}
                  format={{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
                  className="text-5xl font-semibold tracking-tight"
                  style={{ fontFamily: "Poppins, sans-serif" }}
                  duration={600}
                />
              </div>
              {totalNotional > 0 && (
                <p className="text-[#8B8D91] text-sm font-mono mt-1">
                  on ${totalNotional.toFixed(2)} notional
                </p>
              )}
            </div>

            {/* Time range filters */}
            <div className="flex items-center gap-1 bg-[rgba(243,242,238,0.04)] rounded-[8px] p-1">
              {RANGES.map((r) => (
                <button
                  key={r}
                  onClick={() => setRange(r)}
                  className={cn(
                    "px-3 py-1.5 rounded-[6px] text-xs font-mono transition-all",
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

          {/* Chart */}
          <ChartAreaSmooth data={chartData} positive={pnlPositive} />
        </div>

        {/* Stat cards */}
        {statCards.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {statCards.map((s) => (
              <div
                key={s.label}
                className="rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] p-5"
              >
                <div
                  className={cn(
                    "text-2xl font-black mb-1",
                    s.positive === true
                      ? "text-emerald-400"
                      : s.positive === false
                      ? "text-red-400"
                      : "text-[#F3F2EE]"
                  )}
                  style={{ fontFamily: "Poppins, sans-serif" }}
                >
                  <AnimateNumber
                    value={Math.abs(s.decimals != null ? s.value : Math.round(s.value))}
                    prefix={s.prefix ? (s.value < 0 ? `-${s.prefix}` : s.prefix) : undefined}
                    suffix={s.suffix}
                    format={
                      s.decimals != null
                        ? { minimumFractionDigits: s.decimals, maximumFractionDigits: s.decimals }
                        : undefined
                    }
                    className="text-2xl font-black"
                  />
                </div>
                <span className="text-xs text-[#8B8D91] font-mono uppercase tracking-wider">
                  {s.label}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
