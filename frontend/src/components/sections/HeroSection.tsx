import { motion } from "framer-motion";
import { Shield } from "lucide-react";
import MotionButton from "@/components/ui/motion-button";
import { LiquidMetalButton } from "@/components/ui/liquid-metal-button";

const itemVariant = {
  hidden: { opacity: 0, filter: "blur(12px)", y: 20 },
  visible: {
    opacity: 1,
    filter: "blur(0px)",
    y: 0,
    transition: { type: "spring" as const, bounce: 0.25, duration: 1.4 },
  },
};

const containerVariant = {
  visible: { transition: { staggerChildren: 0.1, delayChildren: 0.2 } },
};

const flowSteps = ["Bot", "JSONL", "bytes32", "Mantle", "Verify"];

export function HeroSection() {
  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden bg-[#0B0B0D]">
      {/* Dot-grid background */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              "radial-gradient(circle, rgba(243,242,238,0.09) 1px, transparent 1px)",
            backgroundSize: "36px 36px",
          }}
        />
        {/* Radial fade — dots vanish at edges */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_70%_60%_at_50%_50%,transparent_30%,#0B0B0D_90%)]" />
        {/* Subtle orange bloom at center */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[500px] rounded-full bg-[#E55A1C] opacity-[0.035] blur-[140px]" />
      </div>

      {/* Content */}
      <motion.div
        variants={containerVariant}
        initial="hidden"
        animate="visible"
        className="relative z-10 max-w-5xl mx-auto px-6 text-center flex flex-col items-center"
      >
        {/* Eyebrow badge */}
        <motion.div variants={itemVariant}>
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-[rgba(229,90,28,0.25)] bg-[rgba(229,90,28,0.06)] px-4 py-1.5 backdrop-blur-sm">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#E55A1C] opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#E55A1C]" />
            </span>
            <span className="font-mono tracking-widest uppercase text-[10px] text-[#E55A1C]">
              AI Alpha &amp; Data · Mantle Track
            </span>
          </div>
        </motion.div>

        {/* Headline */}
        <motion.h1
          variants={itemVariant}
          className="text-[clamp(2.8rem,7.5vw,6.5rem)] font-extrabold leading-[0.95] tracking-[-0.04em] text-[#F3F2EE] mb-6"
          style={{ fontFamily: "Bricolage Grotesque, sans-serif" }}
        >
          Every AI decision.
          <br />
          <span className="text-[#E55A1C]">Anchored on Mantle.</span>
        </motion.h1>

        {/* Subline */}
        <motion.p
          variants={itemVariant}
          className="text-[#8B8D91] text-lg md:text-xl max-w-2xl leading-relaxed mb-12"
          style={{ fontFamily: "DM Sans, sans-serif" }}
        >
          Deterministic{" "}
          <code className="font-mono text-[#E55A1C] text-sm bg-[rgba(229,90,28,0.08)] px-1.5 py-0.5 rounded">
            bytes32
          </code>{" "}
          commitments exported from every trade decision. Judges verify on-chain. Zero custody.
          Fully auditable.
        </motion.p>

        {/* CTAs */}
        <motion.div
          variants={itemVariant}
          className="flex flex-wrap items-center justify-center gap-4"
        >
          <MotionButton
            label="View Decisions"
            classes="bg-[#1A1A1E]"
            onClick={() =>
              document.getElementById("decisions")?.scrollIntoView({ behavior: "smooth" })
            }
          />
          <LiquidMetalButton
            label="Verify on Mantle"
            onClick={() =>
              document.getElementById("verify")?.scrollIntoView({ behavior: "smooth" })
            }
          />
        </motion.div>

        {/* Flow diagram */}
        <motion.div
          variants={itemVariant}
          className="mt-16 flex flex-wrap items-center justify-center gap-3 text-xs font-mono text-[#8B8D91]"
        >
          {flowSteps.map((step, i) => (
            <div key={step} className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-[6px] border border-[rgba(243,242,238,0.1)] bg-[rgba(255,255,255,0.03)] backdrop-blur-md shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
                {i === 3 && <Shield className="size-3 text-[#E55A1C]" />}
                <span className={i === 3 ? "text-[#E55A1C]" : ""}>{step}</span>
              </div>
              {i < flowSteps.length - 1 && (
                <span className="text-[rgba(243,242,238,0.18)]">→</span>
              )}
            </div>
          ))}
        </motion.div>
      </motion.div>

      {/* Bottom fade */}
      <div className="absolute bottom-0 left-0 right-0 h-40 z-[2] bg-gradient-to-t from-[#0B0B0D] to-transparent pointer-events-none" />
    </section>
  );
}
