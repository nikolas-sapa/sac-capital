import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, BarChart2 } from "lucide-react";
import type { EquityPosition } from "@/types";
import { AnimateNumber } from "@/components/ui/animated-blur-number";
import { StockMiniChart } from "@/components/ui/stock-mini-chart";
import { cn } from "@/lib/utils";

interface DecisionsSectionProps {
  positions: EquityPosition[];
}

const STATUS_CONFIG = {
  open:      { label: "Open",    dot: "bg-emerald-400", text: "text-emerald-400" },
  closed:    { label: "Closed",  dot: "bg-neutral-500", text: "text-neutral-400" },
  submitted: { label: "Pending", dot: "bg-[#0b7bff]",   text: "text-[#0b7bff]"  },
};

function pnlColor(v: number | null) {
  if (v == null || v === 0) return "text-neutral-400";
  return v > 0 ? "text-emerald-400" : "text-red-400";
}

function AnalysisRow({ label, value }: { label: string; value: string | undefined }) {
  if (!value) return null;
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[9px] font-mono uppercase tracking-widest text-[#8B8D91]">{label}</span>
      <p className="text-[11px] text-[rgba(243,242,238,0.75)] leading-relaxed">{value}</p>
    </div>
  );
}

function PositionCard({ pos, index }: { pos: EquityPosition; index: number }) {
  const [expanded, setExpanded] = useState(false);

  const cfg = STATUS_CONFIG[pos.status as keyof typeof STATUS_CONFIG] ?? STATUS_CONFIG.submitted;
  const activePnl = pos.status === "closed" ? pos.realized_pnl : pos.unrealized_pnl;
  const entryVal = pos.entry_price != null && pos.shares != null ? pos.entry_price * pos.shares : null;
  const pnlPct = activePnl != null && entryVal ? (activePnl / Math.abs(entryVal)) * 100 : null;
  const strategy = pos.strategy?.replace(/_/g, " ") ?? "";
  const analysis = pos.analysis ?? null;
  const hasAnalysis = analysis != null && (analysis.thesis || analysis.catalyst || analysis.reason);
  const markPrice = pos.status === "closed" ? pos.exit_price : pos.mark_price;

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 280, damping: 28, delay: index * 0.05 }}
      className="rounded-[12px] border border-[rgba(243,242,238,0.07)] bg-[#1A1A1E] overflow-hidden hover:border-[rgba(243,242,238,0.12)] transition-colors"
    >
      <div className="p-5 flex flex-col gap-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p
              className="text-2xl font-black text-[#F3F2EE] leading-none tracking-tight"
              style={{ fontFamily: "Poppins, sans-serif" }}
            >
              {pos.ticker}
            </p>
            {strategy && (
              <p className="text-[11px] text-[#8B8D91] mt-1 capitalize leading-tight"
                style={{ fontFamily: "DM Sans, sans-serif" }}>
                {strategy}
              </p>
            )}
          </div>
          <span className={cn("inline-flex items-center gap-1.5 shrink-0 mt-0.5")}>
            <span className={cn("w-1.5 h-1.5 rounded-full", cfg.dot)} />
            <span className={cn("text-[10px] font-mono uppercase tracking-widest", cfg.text)}>
              {cfg.label}
            </span>
          </span>
        </div>

        {/* Price row */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider mb-1">Entry</p>
            <p className="text-sm font-semibold text-[#F3F2EE]" style={{ fontFamily: "DM Sans, sans-serif" }}>
              {pos.entry_price != null ? `$${pos.entry_price.toFixed(2)}` : "—"}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider mb-1">
              {pos.status === "closed" ? "Exit" : "Current"}
            </p>
            <p className="text-sm font-semibold text-[#F3F2EE]" style={{ fontFamily: "DM Sans, sans-serif" }}>
              {markPrice != null ? `$${markPrice.toFixed(2)}` : "—"}
            </p>
          </div>
        </div>

        {/* PnL */}
        <div className="flex items-end justify-between pt-3 border-t border-[rgba(243,242,238,0.05)]">
          <div>
            <p className="text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider mb-1">
              {pos.status === "closed" ? "Realized" : "Unrealized"}
            </p>
            <div className={cn("font-bold", pnlColor(activePnl))}>
              {activePnl != null ? (
                <AnimateNumber
                  value={Math.abs(activePnl)}
                  prefix={activePnl < 0 ? "-$" : "+$"}
                  format={{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
                  className="text-xl font-bold"
                  style={{ fontFamily: "Poppins, sans-serif" }}
                />
              ) : (
                <span className="text-[#8B8D91] text-xl">—</span>
              )}
            </div>
          </div>
          <div className="text-right flex flex-col items-end gap-1">
            {pnlPct != null && (
              <span className={cn("text-sm font-semibold", pnlColor(activePnl))}
                style={{ fontFamily: "DM Sans, sans-serif" }}>
                {activePnl! >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
              </span>
            )}
            {pos.confidence != null && (
              <span className="text-[10px] font-mono text-[#8B8D91]">
                {Math.round(pos.confidence * 100)}% conf
              </span>
            )}
          </div>
        </div>

        {/* Shares + notional */}
        {(pos.shares != null || entryVal != null) && (
          <div className="flex items-center justify-between text-[10px] font-mono text-[#8B8D91]">
            {pos.shares != null && <span>{pos.shares.toFixed(4)} shares</span>}
            {entryVal != null && <span>${entryVal.toFixed(2)} notional</span>}
          </div>
        )}

        {/* Expand toggle */}
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center justify-center gap-1.5 w-full py-2 rounded-[6px] border border-[rgba(243,242,238,0.06)] text-[10px] font-mono uppercase tracking-wider text-[#8B8D91] hover:text-[#F3F2EE] hover:border-[rgba(11,123,255,0.3)] hover:bg-[rgba(11,123,255,0.04)] transition-all"
        >
          <BarChart2 className="size-3 text-[#0b7bff]" />
          {expanded ? "Hide" : "Chart & Analysis"}
          {expanded ? <ChevronUp className="size-3" /> : <ChevronDown className="size-3" />}
        </button>
      </div>

      {/* Expanded: chart + analysis */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="expanded"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5 flex flex-col gap-4 border-t border-[rgba(243,242,238,0.05)]">
              {/* Stock chart */}
              <div className="pt-4">
                <StockMiniChart
                  ticker={pos.ticker}
                  entryPrice={pos.entry_price}
                  entryDate={pos.opened_at}
                  markPrice={markPrice}
                  period="1M"
                />
                <p className="text-[9px] font-mono text-[#8B8D91] mt-1.5 text-center">
                  Orange dot = bot entry · Dashed line = entry price
                </p>
              </div>

              {/* Analysis */}
              {hasAnalysis && (
                <div className="flex flex-col gap-3 pt-1">
                  <p className="text-[9px] font-mono uppercase tracking-widest text-[#0b7bff]">Bot Reasoning</p>
                  <AnalysisRow label="Thesis" value={analysis?.thesis} />
                  <AnalysisRow label="Catalyst" value={analysis?.catalyst} />
                  <AnalysisRow label="Reason" value={analysis?.reason} />
                  <AnalysisRow label="Business quality" value={analysis?.business_quality} />
                  <AnalysisRow label="Valuation" value={analysis?.valuation} />
                  <AnalysisRow label="Balance sheet risk" value={analysis?.balance_sheet_risk} />
                  <AnalysisRow label="Market expectation gap" value={analysis?.market_expectation_gap} />
                  <AnalysisRow label="Invalidation" value={analysis?.invalidation} />
                  {analysis?.evidence_citations && analysis.evidence_citations.length > 0 && (
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[9px] font-mono uppercase tracking-widest text-[#8B8D91]">Evidence</span>
                      <ul className="flex flex-col gap-0.5">
                        {analysis.evidence_citations.map((c, i) => (
                          <li key={i} className="text-[11px] text-[rgba(243,242,238,0.6)] font-mono leading-relaxed">
                            · {c}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {analysis?.challenger_verdict && (
                    <div className="rounded-[6px] border border-[rgba(243,242,238,0.06)] bg-[rgba(243,242,238,0.02)] px-3 py-2">
                      <p className="text-[9px] font-mono uppercase tracking-widest text-[#8B8D91] mb-1">
                        Challenger verdict
                      </p>
                      <p className={cn("text-[11px] font-mono font-bold",
                        analysis.challenger_verdict === "pass" ? "text-emerald-400" :
                        analysis.challenger_verdict === "reject" ? "text-red-400" : "text-amber-400"
                      )}>
                        {analysis.challenger_verdict.toUpperCase()}
                      </p>
                      {analysis.challenger_objections?.map((o, i) => (
                        <p key={i} className="text-[10px] text-[rgba(243,242,238,0.5)] mt-1 leading-relaxed">· {o}</p>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {!hasAnalysis && (
                <p className="text-[10px] font-mono text-[#8B8D91] text-center py-2">
                  No analysis recorded — run the bot with the latest version to capture reasoning.
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  );
}

const FILTERS = ["all", "open", "closed"] as const;
type Filter = typeof FILTERS[number];
const INITIAL_COUNT = 6;

export function DecisionsSection({ positions }: DecisionsSectionProps) {
  const [filter, setFilter] = useState<Filter>("all");
  const [showAll, setShowAll] = useState(false);

  const visible = positions.filter((p) =>
    filter === "all" ? true : p.status === filter
  );
  const displayed = showAll ? visible : visible.slice(0, INITIAL_COUNT);
  const hiddenCount = visible.length - INITIAL_COUNT;

  return (
    <section id="decisions" className="py-24 px-6 bg-[#0B0B0D]">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-10">
          <p className="text-[10px] font-mono tracking-widest uppercase text-[#0b7bff] mb-3">
            Alpaca Paper Portfolio
          </p>
          <h2
            className="text-4xl font-black text-[#F3F2EE]"
            style={{ fontFamily: "Poppins, sans-serif" }}
          >
            Stock Positions
          </h2>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-2 mb-8">
          {FILTERS.map((f) => {
            const count = f === "all" ? positions.length : positions.filter((p) => p.status === f).length;
            return (
              <button
                key={f}
                onClick={() => { setFilter(f); setShowAll(false); }}
                className={cn(
                  "px-4 py-1.5 rounded-full text-xs font-mono uppercase tracking-wider transition-colors border",
                  filter === f
                    ? "bg-[#0b7bff] border-[#0b7bff] text-white"
                    : "border-[rgba(243,242,238,0.1)] text-[#8B8D91] hover:text-[#F3F2EE] hover:border-[rgba(243,242,238,0.2)]"
                )}
              >
                {f} {count > 0 && <span className="ml-1 opacity-70">{count}</span>}
              </button>
            );
          })}
        </div>

        {/* Grid */}
        {visible.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <AnimatePresence mode="popLayout">
              {displayed.map((pos, i) => (
                <PositionCard key={pos.id} pos={pos} index={i} />
              ))}
            </AnimatePresence>
          </div>
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] p-8 text-center"
          >
            <p className="text-[#8B8D91] text-sm font-mono">No {filter} positions.</p>
          </motion.div>
        )}

        {/* Show more / less */}
        {!showAll && hiddenCount > 0 && (
          <div className="mt-6 flex justify-center">
            <motion.button
              onClick={() => setShowAll(true)}
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              transition={{ type: "spring", stiffness: 400, damping: 20 }}
              className="flex items-center gap-2 px-5 py-2.5 rounded-full text-xs font-mono uppercase tracking-wider border border-[rgba(243,242,238,0.12)] text-[#8B8D91] hover:text-[#F3F2EE] hover:border-[rgba(11,123,255,0.4)] hover:shadow-[0_0_16px_rgba(11,123,255,0.15)] transition-all duration-200"
            >
              <span>Show {hiddenCount} more</span>
              <ChevronDown className="size-3.5 text-[#0b7bff]" />
            </motion.button>
          </div>
        )}
        {showAll && visible.length > INITIAL_COUNT && (
          <div className="mt-6 flex justify-center">
            <motion.button
              onClick={() => setShowAll(false)}
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              transition={{ type: "spring", stiffness: 400, damping: 20 }}
              className="flex items-center gap-2 px-5 py-2.5 rounded-full text-xs font-mono uppercase tracking-wider border border-[rgba(243,242,238,0.12)] text-[#8B8D91] hover:text-[#F3F2EE] hover:border-[rgba(11,123,255,0.4)] transition-all duration-200"
            >
              <span>Show less</span>
              <ChevronUp className="size-3.5 text-[#0b7bff]" />
            </motion.button>
          </div>
        )}
      </div>
    </section>
  );
}
