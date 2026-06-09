import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search } from "lucide-react";
import type { Commitment, RegistryEvent } from "@/types";
import { shortHash, formatPct } from "@/data/mantle";
import { cn } from "@/lib/utils";

interface DecisionsSectionProps {
  commitments: Commitment[];
  events: RegistryEvent[];
  explorerBase: string;
  registryAddress: string | undefined;
  status: string;
}

const PAGE_SIZE = 6;

function DecisionCard({ item, index }: { item: Commitment; index: number }) {
  const isEquity = Boolean(
    item.payload.ticker || item.payload.strategy === "equity_analyst"
  );
  const p = item.payload;

  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ type: "spring", stiffness: 300, damping: 30, delay: index * 0.04 }}
      className={cn(
        "rounded-[12px] border bg-[#1A1A1E] p-5",
        isEquity
          ? "border-l-2 border-l-[#E55A1C] border-[rgba(243,242,238,0.06)]"
          : "border-[rgba(243,242,238,0.06)]"
      )}
      style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "1rem" }}
    >
      <div className="min-w-0">
        {isEquity ? (
          <div className="flex items-center gap-2 mb-2">
            <span
              className="text-lg font-black text-[#F3F2EE]"
              style={{ fontFamily: "Geist Mono, monospace" }}
            >
              {p.ticker}
            </span>
            {p.status && (
              <span
                className={cn(
                  "text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-[4px]",
                  p.status === "open"
                    ? "bg-[rgba(229,90,28,0.1)] text-[#E55A1C]"
                    : "bg-[rgba(243,242,238,0.06)] text-[#8B8D91]"
                )}
              >
                {p.status}
              </span>
            )}
          </div>
        ) : (
          <h3 className="text-sm font-semibold text-[#F3F2EE] mb-1 line-clamp-2">{p.question}</h3>
        )}
        <p className="text-xs text-[#8B8D91] line-clamp-2">{p.reason}</p>
      </div>

      <dl className="text-right shrink-0 space-y-1">
        <div>
          <dt className="text-[10px] font-mono text-[#8B8D91] uppercase">Conf</dt>
          <dd className="text-sm font-bold text-[#F3F2EE]">{formatPct(p.confidence)}</dd>
        </div>
        {isEquity ? (
          <div>
            <dt className="text-[10px] font-mono text-[#8B8D91] uppercase">P&L</dt>
            <dd
              className={cn(
                "text-sm font-bold font-mono",
                (p.realized_pnl ?? p.pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"
              )}
            >
              {p.realized_pnl != null
                ? `$${p.realized_pnl.toFixed(2)}`
                : p.pnl != null
                ? `$${p.pnl.toFixed(2)}`
                : "open"}
            </dd>
          </div>
        ) : (
          <div>
            <dt className="text-[10px] font-mono text-[#8B8D91] uppercase">Fair</dt>
            <dd className="text-sm font-bold text-[#F3F2EE]">{formatPct(p.fair_prob)}</dd>
          </div>
        )}
        <div>
          <dt className="text-[10px] font-mono text-[#8B8D91] uppercase">Hash</dt>
          <dd className="text-[10px] font-mono text-[rgba(243,242,238,0.3)]">
            {shortHash(item.bytes32)}
          </dd>
        </div>
      </dl>
    </motion.article>
  );
}

export function DecisionsSection({
  commitments,
  events,
  explorerBase,
  registryAddress,
  status,
}: DecisionsSectionProps) {
  const [search, setSearch] = useState("");
  const [showAll, setShowAll] = useState(false);

  const filtered = useMemo(() => {
    if (!search.trim()) return commitments;
    const q = search.trim().toLowerCase();
    return commitments.filter((c) => c.bytes32.toLowerCase().includes(q));
  }, [commitments, search]);

  const visible = showAll ? filtered : filtered.slice(0, PAGE_SIZE);
  const explorerLink = registryAddress
    ? `${explorerBase.replace(/\/$/, "")}/address/${registryAddress}`
    : "";

  const registryItems = events.length
    ? events
    : commitments.slice(0, 5).map((c, i) => ({
        id: String(i),
        decisionHash: c.bytes32,
        uri: `sample#${i + 1}`,
      }));

  return (
    <section id="decisions" className="py-24 px-6 bg-[#0B0B0D]">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-end justify-between mb-12 flex-wrap gap-4">
          <div>
            <p className="text-[10px] font-mono tracking-widest uppercase text-[#E55A1C] mb-3">
              Decision feed
            </p>
            <h2
              className="text-4xl font-black text-[#F3F2EE]"
              style={{ fontFamily: "Sora, sans-serif" }}
            >
              Auditable AI payloads
            </h2>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-[#8B8D91]" />
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setShowAll(false);
              }}
              placeholder="Filter by hash..."
              className="pl-9 pr-4 py-2.5 rounded-[8px] border border-[rgba(243,242,238,0.08)] bg-[#1A1A1E] text-sm text-[#F3F2EE] placeholder:text-[#8B8D91] outline-none focus:border-[rgba(229,90,28,0.4)] transition-colors font-mono w-64"
            />
          </div>
        </div>

        <div className="grid md:grid-cols-[1fr_320px] gap-6">
          {/* Feed */}
          <div className="space-y-3">
            <AnimatePresence mode="popLayout">
              {visible.length === 0 ? (
                <p className="text-[#8B8D91] text-sm font-mono">
                  No decisions match that hash fragment.
                </p>
              ) : (
                visible.map((item, i) => (
                  <DecisionCard key={item.bytes32} item={item} index={i} />
                ))
              )}
            </AnimatePresence>
            {filtered.length > PAGE_SIZE && !showAll && (
              <button
                onClick={() => setShowAll(true)}
                className="w-full py-3 rounded-[8px] border border-[rgba(243,242,238,0.08)] text-sm font-mono text-[#8B8D91] hover:text-[#F3F2EE] hover:border-[rgba(243,242,238,0.16)] transition-colors"
              >
                Show all {filtered.length} decisions
              </button>
            )}
          </div>

          {/* Registry panel */}
          <aside className="rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] p-6 h-fit">
            <p className="text-[10px] font-mono tracking-widest uppercase text-[#E55A1C] mb-1">
              Mantle registry
            </p>
            <h3
              className="text-lg font-bold text-[#F3F2EE] mb-4"
              style={{ fontFamily: "Sora, sans-serif" }}
            >
              Reputation layer
            </h3>
            <p className="text-xs text-[#8B8D91] mb-4 font-mono">{status}</p>
            <dl className="space-y-3 text-xs font-mono">
              <div className="flex justify-between gap-4">
                <dt className="text-[#8B8D91]">Contract</dt>
                <dd className="text-[rgba(243,242,238,0.5)] text-right break-all">
                  {registryAddress ? shortHash(registryAddress) : "Set env var"}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-[#8B8D91]">Explorer</dt>
                <dd>
                  {explorerLink ? (
                    <a
                      href={explorerLink}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[#E55A1C] hover:underline"
                    >
                      Mantle Sepolia
                    </a>
                  ) : (
                    "Pending"
                  )}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-[#8B8D91]">Events</dt>
                <dd className="text-[#F3F2EE]">
                  {events.length ? `${events.length} live` : "Fallback JSON"}
                </dd>
              </div>
            </dl>
            <div className="mt-4 space-y-2 border-t border-[rgba(243,242,238,0.06)] pt-4">
              {registryItems.map((ev) => (
                <div
                  key={`${ev.id}-${ev.decisionHash}`}
                  className="pl-3 border-l-2 border-[rgba(229,90,28,0.3)] py-1"
                >
                  <strong className="block text-[10px] font-mono text-[#F3F2EE]">
                    #{ev.id} {shortHash(ev.decisionHash)}
                  </strong>
                  <span className="block text-[10px] font-mono text-[#8B8D91] mt-0.5">
                    {ev.uri}
                  </span>
                </div>
              ))}
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}
