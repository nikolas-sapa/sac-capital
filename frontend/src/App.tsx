import { useEffect, useState } from "react";
import type { Hex } from "viem";
import { NavBar } from "@/components/sections/NavBar";
import { HeroSection } from "@/components/sections/HeroSection";
import { HowItWorksSection } from "@/components/sections/HowItWorksSection";
import { DecisionsSection } from "@/components/sections/DecisionsSection";
import { PerformanceSection } from "@/components/sections/PerformanceSection";
import { VerifySection } from "@/components/sections/VerifySection";
import { CTASection } from "@/components/sections/CTASection";
import type { Commitment, RegistryEvent, PerformanceSummary, EquityPosition } from "@/types";
import {
  sha256Hex,
  explorerBase,
  registryAddress,
  rpcUrl,
  createMantleClient,
  createRegistryContract,
} from "@/data/mantle";

function mergeLivePositions(
  live: EquityPosition[],
  staticPositions: EquityPosition[]
): EquityPosition[] {
  const staticByTicker: Record<string, EquityPosition> = {};
  for (const p of staticPositions) staticByTicker[p.ticker] = p;

  const merged = live.map((p) => {
    const meta = staticByTicker[p.ticker];
    return meta
      ? {
          ...p,
          analysis: meta.analysis,
          strategy: meta.strategy || p.strategy,
          confidence: meta.confidence ?? p.confidence,
          entries: meta.entries,
        }
      : p;
  });

  const liveKeys = new Set(live.map((p) => `${p.status}:${p.ticker}`));
  return [
    ...merged,
    ...staticPositions.filter(
      (p) => p.status !== "open" && !liveKeys.has(`${p.status}:${p.ticker}`)
    ),
  ];
}

export default function App() {
  const [commitments, setCommitments] = useState<Commitment[]>([]);
  const [positions, setPositions] = useState<EquityPosition[]>([]);
  const [events, setEvents] = useState<RegistryEvent[]>([]);
  const [verifiedHash, setVerifiedHash] = useState("");
  const [perf, setPerf] = useState<PerformanceSummary | null>(null);

  const selected = commitments[0];

  // Mantle commitments (for VerifySection hash proof)
  useEffect(() => {
    fetch("/mantle_commitments.sample.json")
      .then((r) => r.json())
      .then((data: Commitment[]) => setCommitments(data))
      .catch((err) => console.error("Failed to load mantle commitments:", err));
  }, []);

  // Alpaca equity positions — live prices merged with static analysis metadata
  useEffect(() => {
    async function loadPositions() {
      // Always load static snapshot first for analysis/strategy/confidence fields
      let staticPositions: EquityPosition[] = [];
      try {
        const r = await fetch(`/equity_positions.json?ts=${Date.now()}`, {
          cache: "no-store",
        });
        if (r.ok) {
          staticPositions = await r.json();
        }
      } catch (err) {
        console.error("Failed to load static positions:", err);
      }

      // Try live Alpaca for fresh prices/pnl; merge analysis from static
      try {
        const r = await fetch("/api/positions");
        if (r.ok) {
          const live: EquityPosition[] = await r.json();
          setPositions(mergeLivePositions(live, staticPositions));
          return;
        }
      } catch (err) {
        console.error("Failed to load live positions:", err);
      }

      // Alpaca unavailable — use static snapshot directly
      if (staticPositions.length > 0) {
        setPositions(staticPositions);
      }
    }

    loadPositions();
    const id = setInterval(loadPositions, 30_000);
    return () => clearInterval(id);
  }, []);

  // Performance summary
  useEffect(() => {
    fetch(`/performance_summary.json?ts=${Date.now()}`, { cache: "no-store" })
      .then((r) => r.json())
      .then((data: PerformanceSummary) => setPerf(data))
      .catch((err) => {
        console.error("Failed to load performance summary:", err);
        setPerf(null);
      });
  }, []);

  // Live Mantle registry events.
  // Mantle caps eth_getLogs at 10k blocks, so query a bounded recent window
  // (captures the latest anchored decisions) instead of the full chain.
  useEffect(() => {
    if (!rpcUrl || !registryAddress) return;
    const client = createMantleClient(rpcUrl);
    const contract = createRegistryContract(registryAddress as Hex, client);
    (async () => {
      const latest = await client.getBlockNumber();
      const fromBlock = latest > 9000n ? latest - 9000n : 0n;
      const logs = await contract.getEvents.DecisionRecorded({}, { fromBlock, toBlock: latest });
      // Keep ALL events in the window for the verify-panel membership check;
      // display components can slice for presentation.
      setEvents(
        logs
          .reverse()
          .map((log) => ({
            id: String(log.args.id ?? ""),
            agentId: String(log.args.agentId ?? ""),
            decisionHash: String(log.args.decisionHash ?? ""),
            reporter: String(log.args.reporter ?? ""),
            uri: String(log.args.uri ?? ""),
          }))
      );
    })().catch((err) => console.error("Failed to fetch registry events:", err));
  }, []);

  useEffect(() => {
    if (!selected) return;
    sha256Hex(selected.canonical_json)
      .then(setVerifiedHash)
      .catch((err) => console.error("Hash verification failed:", err));
  }, [selected]);

  return (
    <div className="min-h-screen bg-[#0B0B0D]">
      <NavBar />
      <HeroSection />
<HowItWorksSection />
      <PerformanceSection positions={positions} />
      <DecisionsSection positions={positions} />
      <VerifySection selected={selected} verifiedHash={verifiedHash} events={events} />
      <CTASection />
      <footer className="border-t border-[rgba(243,242,238,0.06)] py-8 px-6 text-center">
        <p className="text-xs font-mono text-[rgba(243,242,238,0.3)]">
          Developed by{" "}
          <a
            href="https://nikolas.helpmarq.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[#E55A1C] hover:text-[#C94A12] transition-colors"
          >
            Nikolas Sapalidis
          </a>
          {" "}· SAC Capital · Developed with Konstantopoulos Ilias &amp; George Apostolakis · DoraHacks AI Alpha &amp; Data
        </p>
      </footer>
    </div>
  );
}
