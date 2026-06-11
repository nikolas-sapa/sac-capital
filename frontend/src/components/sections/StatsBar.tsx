import { AnimateNumber } from "@/components/ui/animated-blur-number";
import type { Commitment, RegistryEvent } from "@/types";

interface StatsBarProps {
  commitments: Commitment[];
  events: RegistryEvent[];
}

export function StatsBar({ commitments, events }: StatsBarProps) {
  const anchored = events.length || commitments.length;
  const resolved = commitments.filter((c) => c.payload.resolved).length;
  const pnl = commitments.reduce((sum, c) => sum + (c.payload.pnl ?? 0), 0);
  const confEntries = commitments.filter((c) => c.payload.confidence != null);
  const avgConf =
    confEntries.length === 0
      ? 0
      : confEntries.reduce((sum, c) => sum + c.payload.confidence!, 0) / confEntries.length;

  const stats = [
    { value: anchored, label: "Decisions anchored", decimals: 0 },
    { value: resolved, label: "Resolved outcomes", decimals: 0 },
    { value: pnl, label: "Paper ROI P&L", prefix: "$", decimals: 2 },
    { value: Math.round(avgConf * 1000) / 10, label: "Avg confidence", suffix: "%", decimals: 1 },
  ] as const;

  return (
    <section className="border-y border-[rgba(243,242,238,0.06)] bg-[#0B0B0D]">
      <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-y md:divide-y-0 divide-[rgba(243,242,238,0.06)]">
        {stats.map((stat) => (
          <div key={stat.label} className="px-8 py-7 flex flex-col gap-1">
            <div style={{ fontFamily: "Sora, sans-serif" }}>
              <AnimateNumber
                value={stat.decimals === 0 ? Math.round(stat.value) : stat.value}
                prefix={"prefix" in stat ? stat.prefix : undefined}
                suffix={"suffix" in stat ? stat.suffix : undefined}
                format={
                  stat.decimals > 0
                    ? { minimumFractionDigits: stat.decimals, maximumFractionDigits: stat.decimals }
                    : undefined
                }
                className="text-3xl font-black text-[#F3F2EE]"
                style={{ fontFamily: "Sora, sans-serif" }}
              />
            </div>
            <span className="text-xs text-[#8B8D91] uppercase tracking-widest font-mono">
              {stat.label}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
