import { Suspense, lazy, useState } from "react";
import { ArrowRight } from "lucide-react";

const Dithering = lazy(() =>
  import("@paper-design/shaders-react").then((mod) => ({ default: mod.Dithering }))
);

export function CTASection() {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <section className="py-12 px-6 bg-[#0B0B0D]">
      <div
        className="relative max-w-7xl mx-auto overflow-hidden rounded-[32px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] min-h-[400px] flex flex-col items-center justify-center"
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        {/* Shader backdrop */}
        <div className="absolute inset-0 z-0 pointer-events-none opacity-30 mix-blend-screen">
          <Suspense fallback={null}>
            <Dithering
              colorBack="#00000000"
              colorFront="#0b7bff"
              shape="warp"
              type="4x4"
              speed={isHovered ? 0.6 : 0.2}
              className="size-full"
              minPixelRatio={1}
            />
          </Suspense>
        </div>

        <div className="relative z-10 text-center px-6 max-w-3xl mx-auto flex flex-col items-center">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-[rgba(11,123,255,0.2)] bg-[rgba(11,123,255,0.06)] px-4 py-1.5 text-[10px] font-mono text-[#0b7bff] uppercase tracking-widest">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#0b7bff] opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#0b7bff]" />
            </span>
            Deployed on Mantle Sepolia
          </div>

          <h2
            className="text-4xl md:text-6xl font-black text-[#F3F2EE] leading-tight mb-6"
            style={{ fontFamily: "Poppins, sans-serif" }}
          >
            Verify it yourself.
          </h2>

          <p className="text-[#8B8D91] text-lg mb-10 max-w-xl">
            Every decision hash is public. Recompute it from the JSON. Compare it to the chain.
          </p>

          <a
            href="https://explorer.sepolia.mantle.xyz/address/0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887"
            target="_blank"
            rel="noopener noreferrer"
            className="group inline-flex h-12 items-center gap-3 rounded-full bg-[#0b7bff] px-8 text-sm font-bold text-white transition-all duration-300 hover:bg-[#0060d9] hover:scale-105 active:scale-95"
          >
            View on Mantle Explorer
            <ArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-1" />
          </a>
        </div>
      </div>
    </section>
  );
}
