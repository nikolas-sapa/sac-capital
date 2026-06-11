import { useRef } from "react";
import { motion, useScroll } from "framer-motion";
import { Bot, FileJson, Hash, Shield, CheckCircle, type LucideIcon } from "lucide-react";

type Step = {
  num: string;
  icon: LucideIcon;
  title: string;
  body: string;
};

const steps: Step[] = [
  {
    num: "01",
    icon: Bot,
    title: "AI Makes a Decision",
    body: "The AI agent runs a multi-stage LLM analysis pipeline on US equities and financial markets, producing structured decisions with confidence scores, strategies, and reasoning.",
  },
  {
    num: "02",
    icon: FileJson,
    title: "Payload Exported to JSONL",
    body: "Each decision is serialized into canonical JSON and exported to a deterministic JSONL artifact. Every field is sorted — no ambiguity in the hash input.",
  },
  {
    num: "03",
    icon: Hash,
    title: "bytes32 Commitment Created",
    body: "Canonical JSON is SHA-256 hashed into a bytes32 commitment. The same payload always produces the same hash — independently reproducible by anyone.",
  },
  {
    num: "04",
    icon: Shield,
    title: "Anchored on Mantle",
    body: "The bytes32 commitment is recorded in the AgentDecisionRegistry smart contract on Mantle Mainnet. Immutable, timestamped, publicly verifiable on-chain.",
  },
  {
    num: "05",
    icon: CheckCircle,
    title: "Independent Verification",
    body: "Judges re-download the payload, recompute the SHA-256 hash, and compare against the on-chain record. No trust required — math closes the loop.",
  },
];

function StackedCard({ step, index }: { step: Step; index: number }) {
  const ref = useRef(null);
  useScroll({ target: ref, offset: ["start end", "end start"] });
  const Icon = step.icon;

  return (
    <div ref={ref} className="sticky" style={{ top: `${80 + index * 24}px` }}>
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ type: "spring", stiffness: 200, damping: 25, delay: 0.05 }}
        className="relative mx-auto max-w-4xl rounded-[20px] border border-[rgba(243,242,238,0.08)] bg-[#1A1A1E] p-8 md:p-12 overflow-hidden"
        style={{ zIndex: index + 1 }}
      >
        {/* Top edge glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-48 h-px bg-gradient-to-r from-transparent via-[rgba(11,123,255,0.4)] to-transparent" />

        <div className="flex items-start gap-6">
          {/* Icon block */}
          <div className="shrink-0 flex flex-col items-center gap-3">
            <div className="w-12 h-12 rounded-[12px] border border-[rgba(11,123,255,0.2)] bg-[rgba(11,123,255,0.06)] flex items-center justify-center">
              <Icon className="size-5 text-[#0b7bff]" />
            </div>
            <span className="text-[10px] font-mono text-[rgba(243,242,238,0.2)] tracking-widest">
              {step.num}
            </span>
          </div>

          {/* Text */}
          <div className="flex-1 min-w-0">
            <h3
              className="text-2xl font-bold text-[#F3F2EE] mb-3 leading-tight"
              style={{ fontFamily: "Sora, sans-serif" }}
            >
              {step.title}
            </h3>
            <p className="text-[#8B8D91] leading-relaxed text-base max-w-2xl">{step.body}</p>
          </div>

          {/* Ghost number */}
          <div
            className="ml-auto shrink-0 text-[rgba(243,242,238,0.04)] text-7xl font-black leading-none select-none"
            style={{ fontFamily: "Sora, sans-serif" }}
          >
            {step.num}
          </div>
        </div>
      </motion.div>
    </div>
  );
}

export function HowItWorksSection() {
  return (
    <section className="py-24 px-6 bg-[#0B0B0D]">
      <div className="max-w-4xl mx-auto mb-16 text-center">
        <p className="text-[10px] font-mono tracking-widest uppercase text-[#0b7bff] mb-4">
          How it works
        </p>
        <h2
          className="text-4xl md:text-5xl font-black text-[#F3F2EE] leading-tight"
          style={{ fontFamily: "Sora, sans-serif" }}
        >
          Your agents are smart.
          <br />
          <span className="text-[#8B8D91]">Their proofs should be too.</span>
        </h2>
      </div>

      <div className="flex flex-col gap-4">
        {steps.map((step, i) => (
          <StackedCard key={step.num} step={step} index={i} />
        ))}
      </div>
    </section>
  );
}
