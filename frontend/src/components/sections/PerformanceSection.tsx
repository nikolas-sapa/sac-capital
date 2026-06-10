import { useMemo } from "react";
import ChartAreaStep from "@/components/ui/chart-area-step";
import { AnimateNumber } from "@/components/ui/animated-blur-number";
import type { EquityPosition, PerformanceSummary } from "@/types";
import { cn } from "@/lib/utils";

interface PerformanceSectionProps {
  positions: EquityPosition[];
  perf: PerformanceSummary | null;
}

export function PerformanceSection({ positions, perf }: PerformanceSectionProps) {
  // Chart: cumulative PnL by position entry date
  const chartData = useMemo(() => {
    // Build per-date PnL contributions
    const byDate: Record<string, number> = {};
    for (const p of positions) {
      const ts = p.opened_at;
      if (!ts) continue;
      const date = ts.slice(5, 10); // MM-DD
      const pnl = (p.unrealized_pnl ?? 0) + (p.realized_pnl ?? 0);
      byDate[date] = (byDate[date] ?? 0) + pnl;
    }

    const real = Object.entries(byDate)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-8)
      .map(([label, value]) => ({ label, value: parseFloat(value.toFixed(2)) }));

    // Pad with zeros for days with no activity (chart needs >= 2 points)
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

  const eq = perf?.equity_trades;
  const openPositions = positions.filter((p) => p.status === "open");
  const totalUnrealized = openPositions.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0);
  const totalNotional = positions
    .filter((p) => p.entry_price != null && p.shares != null)
    .reduce((s, p) => s + p.entry_price! * p.shares!, 0);

  type StatCard = { value: number; label: string; green: boolean; prefix?: string; suffix?: string; decimals?: number };

  const statCards: StatCard[] = eq
    ? [
        { value: positions.length, label: "Total positions", green: false },
        { value: openPositions.length, label: "Open positions", green: openPositions.length > 0 },
        { value: eq.realized_pnl, label: "Realized P&L", green: eq.realized_pnl >= 0, prefix: "$", decimals: 2 },
        { value: totalUnrealized, label: "Unrealized P&L", green: totalUnrealized >= 0, prefix: "$", decimals: 2 },
        { value: Math.round(eq.win_rate * 1000) / 10, label: "Win rate", green: eq.win_rate > 0.5, suffix: "%", decimals: 1 },
        { value: Math.round(eq.avg_confidence * 1000) / 10, label: "Avg confidence", green: false, suffix: "%", decimals: 1 },
      ]
    : [];

  return (
    <section id="performance" className="py-24 px-6 bg-[#0B0B0D]">
      <div className="max-w-6xl mx-auto">
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
          {totalNotional > 0 && (
            <p className="text-[#8B8D91] text-sm font-mono mt-2">
              ${totalNotional.toFixed(2)} total notional deployed
            </p>
          )}
        </div>

        {statCards.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-10">
            {statCards.map((s) => (
              <div
                key={s.label}
                className="rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] p-5"
              >
                <div
                  className={cn("text-2xl font-black mb-1", s.green ? "text-emerald-400" : s.value < 0 ? "text-red-400" : "text-[#F3F2EE]")}
                  style={{ fontFamily: "Poppins, sans-serif" }}
                >
                  <AnimateNumber
                    value={s.decimals ? s.value : Math.round(s.value)}
                    prefix={s.prefix}
                    suffix={s.suffix}
                    format={s.decimals ? { minimumFractionDigits: s.decimals, maximumFractionDigits: s.decimals } : undefined}
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

        {/* Strategy breakdown */}
        {perf && perf.strategies.length > 0 && (
          <div className="mt-8 rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] overflow-hidden">
            <div className="px-6 py-4 border-b border-[rgba(243,242,238,0.06)]">
              <h3 className="text-sm font-bold text-[#F3F2EE]">Strategy breakdown</h3>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[rgba(243,242,238,0.06)]">
                  <th className="px-6 py-3 text-left text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider">Strategy</th>
                  <th className="px-6 py-3 text-right text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider">Positions</th>
                </tr>
              </thead>
              <tbody>
                {perf.strategies.map((s) => (
                  <tr key={s.name} className="border-b border-[rgba(243,242,238,0.04)] last:border-0 hover:bg-[rgba(243,242,238,0.02)]">
                    <td className="px-6 py-3 font-mono text-[#F3F2EE]">{s.name.replace(/_/g, " ")}</td>
                    <td className="px-6 py-3 font-mono text-right text-[#0b7bff]">{s.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
