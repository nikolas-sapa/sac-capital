import { useEffect, useMemo, useState } from "react";
import ChartAreaStep from "@/components/ui/chart-area-step";
import { AnimateNumber } from "@/components/ui/animated-blur-number";
import type { EquityPosition, PortfolioHistoryPoint } from "@/types";
import { cn } from "@/lib/utils";

type TimeRange = "1D" | "1W" | "1M" | "6M" | "1Y" | "All";
const RANGES: TimeRange[] = ["1D", "1W", "1M", "6M", "1Y", "All"];

interface PerformanceSectionProps {
  positions: EquityPosition[];
}

export function PerformanceSection({ positions }: PerformanceSectionProps) {
  const [range, setRange] = useState<TimeRange>("1W");
  const [historyPoints, setHistoryPoints] = useState<PortfolioHistoryPoint[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Fetch real Alpaca portfolio history whenever the range changes
  useEffect(() => {
    setHistoryLoading(true);
    fetch(`/api/portfolio-history?period=${range}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.points?.length) setHistoryPoints(d.points);
        else setHistoryPoints([]);
      })
      .catch(() => setHistoryPoints([]))
      .finally(() => setHistoryLoading(false));
  }, [range]);

  // Live total unrealized P&L from positions (for the big number)
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

  // Period P&L = last point in history (what the portfolio gained/lost over the period)
  const periodPnl =
    historyPoints.length > 0 ? historyPoints[historyPoints.length - 1].value : totalUnrealized;
  const pnlPositive = periodPnl >= 0;

  // Fallback chart when API unavailable: flat line from position open dates
  const fallbackPoints = useMemo<PortfolioHistoryPoint[]>(() => {
    const today = new Date();
    const days: PortfolioHistoryPoint[] = [];
    const totalPnl = positions.reduce(
      (s, p) => s + (p.unrealized_pnl ?? 0) + (p.realized_pnl ?? 0), 0
    );
    for (let i = 6; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const mm = String(d.getMonth() + 1).padStart(2, "0");
      const dd = String(d.getDate()).padStart(2, "0");
      days.push({ label: `${mm}/${dd}`, value: i === 0 ? totalPnl : 0 });
    }
    return days;
  }, [positions]);

  const chartData =
    historyPoints.length > 0 ? historyPoints : fallbackPoints;

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

        {/* Big P&L card — period selector lives here */}
        <div className="mb-10 rounded-[16px] border border-[rgba(243,242,238,0.07)] bg-[#1A1A1E] p-8">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-6">
            <div>
              <p className="text-[10px] font-mono tracking-widest uppercase text-[#8B8D91] mb-3">
                {range === "1D" ? "Today's P&L" : `${range} P&L`}
              </p>
              <div className={cn(pnlPositive ? "text-emerald-400" : "text-red-400")}>
                <AnimateNumber
                  value={Math.abs(periodPnl)}
                  prefix={periodPnl < 0 ? "-$" : "+$"}
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

            {/* Period selector */}
            <div className="flex flex-wrap items-center gap-1 bg-[rgba(243,242,238,0.04)] rounded-[8px] p-1 self-start">
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

        {/* Chart */}
        <div className={cn("transition-opacity duration-200", historyLoading && "opacity-50")}>
          <ChartAreaStep
            data={chartData}
            title="Portfolio P&L"
            subtitle={`${range} · Alpaca portfolio history`}
          />
        </div>
      </div>
    </section>
  );
}
