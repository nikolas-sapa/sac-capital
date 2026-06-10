import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TrendingUp, TrendingDown, Clock, CheckCircle, Circle } from "lucide-react";
import type { EquityPosition } from "@/types";
import { AnimateNumber } from "@/components/ui/animated-blur-number";
import { cn } from "@/lib/utils";

interface DecisionsSectionProps {
  positions: EquityPosition[];
}

const STATUS_CONFIG = {
  open:      { label: "Open",      color: "text-emerald-400", border: "border-emerald-400/30", bg: "bg-emerald-400/10",  Icon: TrendingUp },
  closed:    { label: "Closed",    color: "text-neutral-400", border: "border-neutral-400/30", bg: "bg-neutral-400/10",  Icon: CheckCircle },
  submitted: { label: "Pending",   color: "text-[#0b7bff]",   border: "border-[#0b7bff]/30",  bg: "bg-[#0b7bff]/10",    Icon: Clock },
};

function pnlColor(v: number | null) {
  if (v == null || v === 0) return "text-neutral-400";
  return v > 0 ? "text-emerald-400" : "text-red-400";
}

function PositionCard({ pos, index }: { pos: EquityPosition; index: number }) {
  const cfg = STATUS_CONFIG[pos.status as keyof typeof STATUS_CONFIG] ?? STATUS_CONFIG.submitted;
  const { Icon } = cfg;
  const activePnl = pos.status === "closed" ? pos.realized_pnl : pos.unrealized_pnl;
  const entryVal = pos.entry_price != null && pos.shares != null ? pos.entry_price * pos.shares : null;
  const pnlPct = activePnl != null && entryVal ? (activePnl / Math.abs(entryVal)) * 100 : null;

  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ type: "spring" as const, stiffness: 280, damping: 28, delay: index * 0.05 }}
      className="rounded-[12px] border border-[rgba(243,242,238,0.07)] bg-[#1A1A1E] p-5 flex flex-col gap-4 hover:border-[rgba(243,242,238,0.14)] transition-colors"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-[8px] bg-[rgba(11,123,255,0.12)] border border-[rgba(11,123,255,0.2)] flex items-center justify-center">
            <span className="font-mono font-bold text-[#92dbe0] text-xs">{pos.ticker}</span>
          </div>
          <div>
            <p className="font-bold text-[#F3F2EE] text-sm leading-tight">{pos.ticker}</p>
            <p className="text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider mt-0.5">{pos.strategy.replace(/_/g, " ")}</p>
          </div>
        </div>
        <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-mono uppercase tracking-wider border", cfg.color, cfg.border, cfg.bg)}>
          <Icon className="size-3" />
          {cfg.label}
        </span>
      </div>

      {/* Price row */}
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <p className="text-[#8B8D91] font-mono mb-1 text-[10px] uppercase tracking-wider">Entry</p>
          <p className="text-[#F3F2EE] font-mono font-medium">
            {pos.entry_price != null ? `$${pos.entry_price.toFixed(2)}` : "—"}
          </p>
        </div>
        <div>
          <p className="text-[#8B8D91] font-mono mb-1 text-[10px] uppercase tracking-wider">
            {pos.status === "closed" ? "Exit" : "Mark"}
          </p>
          <p className="text-[#F3F2EE] font-mono font-medium">
            {(pos.status === "closed" ? pos.exit_price : pos.mark_price) != null
              ? `$${(pos.status === "closed" ? pos.exit_price! : pos.mark_price!).toFixed(2)}`
              : "—"}
          </p>
        </div>
      </div>

      {/* PnL */}
      <div className="flex items-center justify-between pt-3 border-t border-[rgba(243,242,238,0.05)]">
        <div>
          <p className="text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider mb-1">
            {pos.status === "closed" ? "Realized P&L" : "Unrealized P&L"}
          </p>
          <div className={cn("text-lg font-bold font-mono", pnlColor(activePnl))}>
            {activePnl != null ? (
              <AnimateNumber
                value={Math.abs(activePnl)}
                prefix={activePnl < 0 ? "-$" : "+$"}
                format={{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
                className="text-lg font-bold"
              />
            ) : (
              <span className="text-[#8B8D91]">—</span>
            )}
          </div>
        </div>
        <div className="text-right">
          {pnlPct != null && (
            <span className={cn("text-sm font-mono font-bold", pnlColor(activePnl))}>
              {activePnl! >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
            </span>
          )}
          {pos.confidence != null && (
            <p className="text-[10px] font-mono text-[#8B8D91] mt-1">
              {Math.round(pos.confidence * 100)}% conf
            </p>
          )}
        </div>
      </div>

      {/* Shares / value */}
      <div className="flex items-center gap-2 text-[10px] font-mono text-[#8B8D91]">
        <Circle className="size-2.5 fill-current" />
        <span>{pos.shares != null ? `${pos.shares.toFixed(4)} shares` : "—"}</span>
        {entryVal != null && (
          <span className="ml-auto">${entryVal.toFixed(2)} notional</span>
        )}
      </div>
    </motion.article>
  );
}

const FILTERS = ["all", "open", "submitted", "closed"] as const;
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

  const totalUnrealized = positions
    .filter((p) => p.status === "open")
    .reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0);

  const totalRealized = positions
    .filter((p) => p.status === "closed")
    .reduce((s, p) => s + (p.realized_pnl ?? 0), 0);

  return (
    <section id="decisions" className="py-24 px-6 bg-[#0B0B0D]">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-10 flex flex-col md:flex-row md:items-end md:justify-between gap-6">
          <div>
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

          {/* Summary stats */}
          <div className="flex gap-6">
            <div className="text-right">
              <p className="text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider mb-1">Unrealized</p>
              <div className={cn("text-xl font-bold font-mono", pnlColor(totalUnrealized))}>
                <AnimateNumber
                  value={Math.abs(totalUnrealized)}
                  prefix={totalUnrealized < 0 ? "-$" : "+$"}
                  format={{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
                  className="text-xl font-bold"
                />
              </div>
            </div>
            <div className="text-right">
              <p className="text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider mb-1">Realized</p>
              <div className={cn("text-xl font-bold font-mono", pnlColor(totalRealized))}>
                <AnimateNumber
                  value={Math.abs(totalRealized)}
                  prefix={totalRealized < 0 ? "-$" : "+$"}
                  format={{ minimumFractionDigits: 2, maximumFractionDigits: 2 }}
                  className="text-xl font-bold"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-2 mb-8">
          {FILTERS.map((f) => {
            const count = f === "all" ? positions.length : positions.filter((p) => p.status === f).length;
            return (
              <button
                key={f}
                onClick={() => setFilter(f)}
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
        <AnimatePresence mode="popLayout">
          {visible.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {displayed.map((pos, i) => (
                <PositionCard key={pos.id} pos={pos} index={i} />
              ))}
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
        </AnimatePresence>

        {/* Show more / less */}
        {hiddenCount > 0 && (
          <div className="mt-6 flex justify-center">
            <button
              onClick={() => setShowAll((v) => !v)}
              className="px-5 py-2 rounded-full text-xs font-mono uppercase tracking-wider border border-[rgba(243,242,238,0.1)] text-[#8B8D91] hover:text-[#F3F2EE] hover:border-[rgba(243,242,238,0.2)] transition-colors"
            >
              {showAll ? "Show less" : `Show ${hiddenCount} more`}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
