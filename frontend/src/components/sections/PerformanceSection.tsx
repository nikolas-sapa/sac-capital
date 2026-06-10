import { useMemo } from "react";
import ChartAreaStep from "@/components/ui/chart-area-step";
import { AnimateNumber } from "@/components/ui/animated-blur-number";
import type { EquityPosition } from "@/types";
import { cn } from "@/lib/utils";

interface PerformanceSectionProps {
  positions: EquityPosition[];
}

export function PerformanceSection({ positions }: PerformanceSectionProps) {
  const chartData = useMemo(() => {
    const byDate: Record<string, number> = {};
    for (const p of positions) {
      const ts = p.opened_at;
      if (!ts) continue;
      const date = ts.slice(5, 10);
      const pnl = (p.unrealized_pnl ?? 0) + (p.realized_pnl ?? 0);
      byDate[date] = (byDate[date] ?? 0) + pnl;
    }

    const real = Object.entries(byDate)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-8)
      .map(([label, value]) => ({ label, value: parseFloat(value.toFixed(2)) }));

    if (real.length < 2) {
      const pad: { label: string; value: number }[] = [];
      for (let i = 7; i >= 1; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        const mm = String(d.getMonth() + 1).padStart(2, "0");
        const dd = String(d.getDate()).padStart(2, "0");
        pad.push({ label: `${mm}-${dd}`, value: 0 });
      }
      return [...pad, ...real];
    }
    return real;
  }, [positions]);

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

  type StatCard = { value: number; label: string; positive: boolean | null; prefix?: string; suffix?: string; decimals?: number };

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
          <h2
            className="text-4xl font-black text-[#F3F2EE]"
            style={{ fontFamily: "Poppins, sans-serif" }}
          >
            Portfolio Performance
          </h2>
        </div>

        {/* Big animated P&L — above the chart */}
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

        {/* Stat cards — all from live positions */}
        {statCards.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-10">
            {statCards.map((s) => (
              <div
                key={s.label}
                className="rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] p-5"
              >
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
                <span className="text-xs text-[#8B8D91] font-mono uppercase tracking-wider">
                  {s.label}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* P&L chart */}
        <ChartAreaStep
          data={chartData}
          title="Portfolio P&L"
          subtitle="Daily unrealized + realized PnL"
        />
      </div>
    </section>
  );
}
