import { useEffect, useState } from "react";
import type { Hex } from "viem";
import { NavBar } from "@/components/sections/NavBar";
import { HeroSection } from "@/components/sections/HeroSection";
import { StatsBar } from "@/components/sections/StatsBar";
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
      .catch(() => {});
  }, []);

  // Alpaca equity positions — live API with static fallback
  useEffect(() => {
    async function loadPositions() {
      try {
        const r = await fetch("/api/positions");
        if (r.ok) {
          const data: EquityPosition[] = await r.json();
          setPositions(data);
          return;
        }
      } catch {}
      // fallback to static snapshot
      try {
        const r = await fetch("/equity_positions.json");
        if (r.ok) setPositions(await r.json());
      } catch {}
    }

    loadPositions();
    const id = setInterval(loadPositions, 30_000);
    return () => clearInterval(id);
  }, []);

  // Performance summary
  useEffect(() => {
    fetch("/performance_summary.json")
      .then((r) => r.json())
      .then((data: PerformanceSummary) => setPerf(data))
      .catch(() => setPerf(null));
  }, []);

  // Live Mantle registry events
  useEffect(() => {
    if (!rpcUrl || !registryAddress) return;
    const client = createMantleClient(rpcUrl);
    const contract = createRegistryContract(registryAddress as Hex, client);
    contract.getEvents
      .DecisionRecorded()
      .then((logs) => {
        setEvents(
          logs
            .slice(-8)
            .reverse()
            .map((log) => ({
              id: String(log.args.id ?? ""),
              agentId: String(log.args.agentId ?? ""),
              decisionHash: String(log.args.decisionHash ?? ""),
              reporter: String(log.args.reporter ?? ""),
              uri: String(log.args.uri ?? ""),
            }))
        );
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selected) return;
    sha256Hex(selected.canonical_json).then(setVerifiedHash);
  }, [selected]);

  return (
    <div className="min-h-screen bg-[#0B0B0D]">
      <NavBar />
      <HeroSection />
      <StatsBar commitments={commitments} events={events} />
      <HowItWorksSection />
      <PerformanceSection positions={positions} />
      <DecisionsSection positions={positions} />
      <VerifySection selected={selected} verifiedHash={verifiedHash} />
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
          {" "}· SAC Capital · Mantle-Verifiable AI Trading Agent · DoraHacks AI Alpha &amp; Data
        </p>
      </footer>
    </div>
  );
}
