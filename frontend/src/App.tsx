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
  canonicalJson,
  sha256Hex,
  explorerBase,
  registryAddress,
  rpcUrl,
  createMantleClient,
  createRegistryContract,
} from "@/data/mantle";

function wrappedPayload(c: Commitment) {
  return {
    kind: c.kind,
    payload: c.payload,
    schema_version: c.schema_version,
    source: c.source,
  };
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
      .catch(() => {});
  }, []);

  // Alpaca equity positions
  useEffect(() => {
    fetch("/equity_positions.json")
      .then((r) => r.json())
      .then((data: EquityPosition[]) => setPositions(data))
      .catch(() => {});
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
    sha256Hex(canonicalJson(wrappedPayload(selected))).then(setVerifiedHash);
  }, [selected]);

  return (
    <div className="min-h-screen bg-[#0B0B0D]">
      <NavBar />
      <HeroSection />
      <StatsBar commitments={commitments} events={events} />
      <HowItWorksSection />
      <DecisionsSection positions={positions} />
      <PerformanceSection positions={positions} perf={perf} />
      <VerifySection selected={selected} verifiedHash={verifiedHash} />
      <CTASection />
      <footer className="border-t border-[rgba(243,242,238,0.06)] py-8 px-6 text-center">
        <p className="text-xs font-mono text-[rgba(243,242,238,0.2)]">
          Mantle-Verifiable AI Prediction Agent · DoraHacks AI Alpha &amp; Data ·
          Paper-trading only — no live custody
        </p>
      </footer>
    </div>
  );
}
