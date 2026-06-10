import { motion } from "framer-motion";
import { Shield } from "lucide-react";
import { ShaderGradientCanvas, ShaderGradient } from "@shadergradient/react";
import MotionButton from "@/components/ui/motion-button";
import { LiquidMetalButton } from "@/components/ui/liquid-metal-button";

const itemVariant = {
  hidden: { opacity: 0, y: 24 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: "spring" as const, bounce: 0.2, duration: 1.2 },
  },
};

const containerVariant = {
  visible: { transition: { staggerChildren: 0.1, delayChildren: 0.15 } },
};

const flowSteps = ["Bot", "JSONL", "bytes32", "Mantle", "Verify"];

export function HeroSection() {
  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden bg-[#0B0B0D]">
      {/* ShaderGradient — hero-digital-success exact settings */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <ShaderGradientCanvas
          style={{ position: "absolute", top: 0, left: 0, width: "100vw", height: "100vh" }}
          pixelDensity={1}
          pointerEvents="none"
        >
          <ShaderGradient
            type="sphere"
            animate="on"
            wireframe={false}
            shader="defaults"
            uTime={0}
            uSpeed={0.3}
            uStrength={0.3}
            uDensity={0.8}
            uFrequency={5.5}
            uAmplitude={3.2}
            positionX={-0.1}
            positionY={0}
            positionZ={0}
            rotationX={0}
            rotationY={130}
            rotationZ={70}
            color1="#92dbe0"
            color2="#0b7bff"
            color3="#3865cf"
            reflection={0.4}
            cAzimuthAngle={270}
            cPolarAngle={180}
            cDistance={0.5}
            cameraZoom={15.1}
            lightType="env"
            brightness={0.8}
            envPreset="city"
            grain="on"
            toggleAxis={false}
            zoomOut={false}
            hoverState=""
            enableTransition={false}
          />
        </ShaderGradientCanvas>
        {/* Dark vignette so text stays readable */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_80%_at_50%_50%,transparent_20%,rgba(11,11,13,0.72)_70%,#0B0B0D_100%)]" />
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
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-[rgba(11,123,255,0.3)] bg-[rgba(11,11,13,0.6)] px-4 py-1.5 backdrop-blur-sm">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#92dbe0] opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#92dbe0]" />
            </span>
            <span className="font-mono tracking-widest uppercase text-[10px] text-[#92dbe0]">
              AI Alpha &amp; Data · Mantle Track
            </span>
          </div>
        </motion.div>

        {/* Headline — wave animation: white → orange+blue sweep → dark */}
        <motion.h1
          variants={itemVariant}
          className="hero-wave-text text-[clamp(3rem,9vw,8rem)] font-bold leading-[0.92] tracking-[-0.04em] mb-6"
          style={{ fontFamily: "Poppins, sans-serif" }}
        >
          Every AI decision.
          <br />
          Anchored on Mantle.
        </motion.h1>

        {/* Subline */}
        <motion.p
          variants={itemVariant}
          className="text-neutral-200 text-lg md:text-xl max-w-2xl leading-relaxed mb-12 font-light"
          style={{ fontFamily: "DM Sans, sans-serif" }}
        >
          Deterministic{" "}
          <code className="font-mono text-[#92dbe0] text-sm bg-[rgba(146,219,224,0.1)] px-1.5 py-0.5 rounded">
            bytes32
          </code>{" "}
          commitments from every trade decision. Judges verify on-chain. Zero custody.
          Fully auditable.
        </motion.p>

        {/* CTAs */}
        <motion.div
          variants={itemVariant}
          className="flex flex-wrap items-center justify-center gap-4"
        >
          <MotionButton
            label="View Decisions"
            classes="bg-[rgba(26,26,30,0.8)] backdrop-blur-sm"
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
          className="mt-16 flex flex-wrap items-center justify-center gap-3 text-xs font-mono text-neutral-500"
        >
          {flowSteps.map((step, i) => (
            <div key={step} className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-[6px] border border-[rgba(255,255,255,0.08)] bg-[rgba(11,11,13,0.7)] backdrop-blur-md">
                {i === 3 && <Shield className="size-3 text-[#0b7bff]" />}
                <span className={i === 3 ? "text-[#0b7bff]" : "text-neutral-400"}>{step}</span>
              </div>
              {i < flowSteps.length - 1 && (
                <span className="text-[rgba(255,255,255,0.15)]">→</span>
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
