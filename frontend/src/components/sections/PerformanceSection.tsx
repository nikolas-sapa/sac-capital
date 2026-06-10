import { useMemo } from "react";
import ChartAreaStep from "@/components/ui/chart-area-step";
import { AnimateNumber } from "@/components/ui/animated-blur-number";
import type { Commitment, PerformanceSummary } from "@/types";
import { cn } from "@/lib/utils";

interface PerformanceSectionProps {
  commitments: Commitment[];
  perf: PerformanceSummary | null;
}

export function PerformanceSection({ commitments, perf }: PerformanceSectionProps) {
  const chartData = useMemo(() => {
    const groups: Record<string, number> = {};
    for (const c of commitments) {
      const ts = c.payload.timestamp || c.payload.opened_at;
      if (!ts) continue;
      const date = ts.slice(5, 10);
      groups[date] = (groups[date] || 0) + 1;
    }
    return Object.entries(groups)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-8)
      .map(([label, value]) => ({ label, value }));
  }, [commitments]);

  const eq = perf?.equity_trades;

  type StatCard = {
    value: number;
    label: string;
    green: boolean;
    prefix?: string;
    suffix?: string;
    decimals?: number;
  };

  const statCards: StatCard[] = eq
    ? [
        { value: perf!.total_commitments, label: "Total decisions anchored", green: false },
        { value: eq.total, label: "Equity trades total", green: false },
        { value: eq.realized_pnl, label: "Closed P&L ($)", green: eq.realized_pnl >= 0, prefix: "$", decimals: 2 },
        { value: Math.round(eq.win_rate * 1000) / 10, label: "Win rate", green: eq.win_rate > 0.5, suffix: "%", decimals: 1 },
        { value: Math.round(eq.avg_confidence * 1000) / 10, label: "Avg confidence", green: false, suffix: "%", decimals: 1 },
        { value: eq.open, label: "Open positions", green: false },
      ]
    : [];

  return (
    <section id="performance" className="py-24 px-6 bg-[#0B0B0D]">
      <div className="max-w-6xl mx-auto">
        <div className="mb-12">
          <p className="text-[10px] font-mono tracking-widest uppercase text-[#0b7bff] mb-3">
            Performance summary
          </p>
          <h2
            className="text-4xl font-black text-[#F3F2EE]"
            style={{ fontFamily: "Sora, sans-serif" }}
          >
            AI trading track record
          </h2>
        </div>

        {statCards.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-10">
            {statCards.map((s) => (
              <div
                key={s.label}
                className="rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] p-5"
              >
                <div
                  className={cn("text-2xl font-black mb-1", s.green ? "text-emerald-400" : "text-[#F3F2EE]")}
                  style={{ fontFamily: "Sora, sans-serif" }}
                >
                  <AnimateNumber
                    value={s.decimals ? s.value : Math.round(s.value)}
                    prefix={s.prefix}
                    suffix={s.suffix}
                    format={
                      s.decimals
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

        {chartData.length > 1 ? (
          <ChartAreaStep data={chartData} title="Decisions" subtitle="Anchored decisions by date" />
        ) : (
          <div className="rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] p-8 text-center">
            <p className="text-[#8B8D91] text-sm font-mono">
              Accumulating decision history for chart...
            </p>
          </div>
        )}

        {perf && perf.strategies.length > 0 && (
          <div className="mt-8 rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] overflow-hidden">
            <div className="px-6 py-4 border-b border-[rgba(243,242,238,0.06)]">
              <h3 className="text-sm font-bold text-[#F3F2EE]">Strategy breakdown</h3>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[rgba(243,242,238,0.06)]">
                  <th className="px-6 py-3 text-left text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider">
                    Strategy
                  </th>
                  <th className="px-6 py-3 text-right text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider">
                    Decisions
                  </th>
                </tr>
              </thead>
              <tbody>
                {perf.strategies.map((s) => (
                  <tr
                    key={s.name}
                    className="border-b border-[rgba(243,242,238,0.04)] last:border-0 hover:bg-[rgba(243,242,238,0.02)]"
                  >
                    <td className="px-6 py-3 font-mono text-[#F3F2EE]">{s.name}</td>
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
