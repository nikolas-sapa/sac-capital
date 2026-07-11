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

function positionReturnPct(pos: EquityPosition): number | null {
  const endPrice = pos.status === "closed" ? pos.exit_price : pos.mark_price;
  if (endPrice == null || endPrice <= 0) return null;

  const entryPrices = pos.entries?.length
    ? pos.entries.map((entry) => entry.price).filter((price) => price > 0)
    : pos.entry_price != null && pos.entry_price > 0
      ? [pos.entry_price]
      : [];
  if (entryPrices.length === 0) return null;

  const returns = entryPrices.map((entryPrice) => (endPrice / entryPrice - 1) * 100);
  return returns.reduce((sum, value) => sum + value, 0) / returns.length;
}

export function PerformanceSection({ positions }: PerformanceSectionProps) {
  const [range, setRange] = useState<TimeRange>("1W");
  const [chartUnit, setChartUnit] = useState<"$" | "%">("$");
  const [historyPoints, setHistoryPoints] = useState<PortfolioHistoryPoint[]>([]);
  const [apiTotalPnl, setApiTotalPnl] = useState<number | null>(null);
  const [baseValue, setBaseValue] = useState<number | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => {
    setHistoryLoading(true);
    fetch(`/api/portfolio-history?period=${range}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.points?.length) {
          setHistoryPoints(d.points);
          setApiTotalPnl(d.totalPnl ?? null);
          setBaseValue(d.base_value ?? null);
        } else {
          setHistoryPoints([]);
          setApiTotalPnl(null);
          setBaseValue(null);
        }
      })
      .catch(() => { setHistoryPoints([]); setApiTotalPnl(null); setBaseValue(null); })
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

  // Period P&L: use API-provided totalPnl when available (sum of daily bars for multi-day,
  // or last intraday point for 1D). Falls back to live unrealized when no API data.
  const periodPnl = apiTotalPnl ?? (historyPoints.length > 0
    ? historyPoints[historyPoints.length - 1].value
    : totalUnrealized);
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

  const rawChartData =
    historyPoints.length > 0 ? historyPoints : fallbackPoints;

  // % mode: express each point as return vs. period-start equity (same curve, relabeled).
  const canShowPct = chartUnit === "%" && baseValue != null && baseValue > 0;
  const chartData = canShowPct
    ? rawChartData.map((p) => ({ label: p.label, value: (p.value / baseValue!) * 100 }))
    : rawChartData;

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

  // The 21-day time-stop bug force-sold positions. The ones it sold at a LOSS
  // have since recovered above their forced-exit price, so that realized loss is
  // a bug artifact — exclude those from the headline return. Winning bug-closed
  // exits were real gains and are kept. Disclosed in the footnote below.
  const isBugLossExit = (p: EquityPosition) =>
    p.status === "closed" && p.exit_reason === "time_stop" && (p.realized_pnl ?? 0) < 0;

  const { collectiveUnweightedReturn, bugExcludedCount } = useMemo(() => {
    const returns: number[] = [];
    let excluded = 0;
    for (const position of positions) {
      if (isBugLossExit(position)) {
        excluded += 1;
        continue;
      }
      // Equal-weight the actual stock positions only. Skip unfilled orders
      // (`submitted`) and expired contracts — they sit near 0% and dilute the
      // real per-stock performance the average is meant to show.
      if (position.status !== "open" && position.status !== "closed") continue;
      const pct = positionReturnPct(position);
      if (pct == null) continue;
      returns.push(pct);
    }
    return {
      collectiveUnweightedReturn:
        returns.length === 0 ? null : returns.reduce((s, v) => s + v, 0) / returns.length,
      bugExcludedCount: excluded,
    };
  }, [positions]);

  // Realized (closed) vs unrealized (open) P&L. Realized is the true, factual
  // total across all closed trades (bug losses included) — not adjusted.
  const realizedPnl = positions.reduce((s, p) => s + (p.realized_pnl ?? 0), 0);
  const unrealizedPnl = openPositions.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0);

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

        {/* Collective unweighted return */}
        {collectiveUnweightedReturn != null && (
          <div className="mb-10 rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] p-6">
            <p className="text-[10px] font-mono tracking-widest uppercase text-[#8B8D91] mb-2">
              Collective Unweighted Return
            </p>
            <div
              className={cn(
                "text-4xl font-black",
                collectiveUnweightedReturn >= 0 ? "text-emerald-400" : "text-red-400"
              )}
              style={{ fontFamily: "Poppins, sans-serif" }}
            >
              {collectiveUnweightedReturn >= 0 ? "+" : ""}{collectiveUnweightedReturn.toFixed(1)}%
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-[8px] border border-[rgba(243,242,238,0.06)] bg-[#0B0B0D] p-4">
                <p className="text-[10px] font-mono tracking-widest uppercase text-[#8B8D91] mb-1">
                  Realized P&L
                </p>
                <div className={cn("text-xl font-black", realizedPnl >= 0 ? "text-emerald-400" : "text-red-400")} style={{ fontFamily: "Poppins, sans-serif" }}>
                  {realizedPnl < 0 ? "-$" : "+$"}{Math.abs(realizedPnl).toFixed(2)}
                </div>
              </div>
              <div className="rounded-[8px] border border-[rgba(243,242,238,0.06)] bg-[#0B0B0D] p-4">
                <p className="text-[10px] font-mono tracking-widest uppercase text-[#8B8D91] mb-1">
                  Unrealized P&L
                </p>
                <div className={cn("text-xl font-black", unrealizedPnl >= 0 ? "text-emerald-400" : "text-red-400")} style={{ fontFamily: "Poppins, sans-serif" }}>
                  {unrealizedPnl < 0 ? "-$" : "+$"}{Math.abs(unrealizedPnl).toFixed(2)}
                </div>
              </div>
            </div>
            <p className="mt-3 text-xs font-mono text-[#8B8D91]">
              Equal-weighted average of filled stock positions — each stock counts the same regardless
              of position size. Excludes unfilled orders and expired contracts.
            </p>
            {bugExcludedCount > 0 && (
              <p className="mt-1 text-xs font-mono text-[#8B8D91]">
                Excludes {bugExcludedCount} position{bugExcludedCount === 1 ? "" : "s"} the 21-day
                time-stop bug (now fixed) sold at a loss; those tickers have since recovered above their
                forced-exit price. Winning bug-closed exits are kept. Realized P&amp;L above is the true
                total, losses included.
              </p>
            )}
          </div>
        )}

        {/* Chart */}
        <div className={cn("transition-opacity duration-200", historyLoading && "opacity-50")}>
          {/* $ / % toggle — same curve, relabeled units */}
          <div className="mb-3 flex items-center gap-1 bg-[rgba(243,242,238,0.04)] rounded-[8px] p-1 w-fit">
            {(["$", "%"] as const).map((u) => (
              <button
                key={u}
                onClick={() => setChartUnit(u)}
                className={cn(
                  "px-3 py-1.5 rounded-[6px] text-xs font-mono transition-all",
                  u === chartUnit
                    ? "bg-[#0b7bff] text-white"
                    : "text-[#8B8D91] hover:text-[#F3F2EE] hover:bg-[rgba(243,242,238,0.06)]"
                )}
              >
                {u === "$" ? "$ P&L" : "% Return"}
              </button>
            ))}
          </div>
          <ChartAreaStep
            data={chartData}
            unit={canShowPct ? "%" : "$"}
            title={canShowPct ? "Portfolio Return" : "Portfolio P&L"}
            subtitle={`${range} · Alpaca portfolio history`}
          />
        </div>
      </div>
    </section>
  );
}
