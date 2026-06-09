import { useState } from "react";
import { CheckCircle, Copy } from "lucide-react";
import { canonicalJson } from "@/data/mantle";
import type { Commitment } from "@/types";

function wrappedPayload(c: Commitment) {
  return {
    kind: c.kind,
    payload: c.payload,
    schema_version: c.schema_version,
    source: c.source,
  };
}

interface VerifySectionProps {
  selected: Commitment | undefined;
  verifiedHash: string;
}

export function VerifySection({ selected, verifiedHash }: VerifySectionProps) {
  const [copied, setCopied] = useState<"json" | "hash" | null>(null);

  const copy = async (text: string, which: "json" | "hash") => {
    await navigator.clipboard.writeText(text);
    setCopied(which);
    setTimeout(() => setCopied(null), 1200);
  };

  const jsonStr = selected ? canonicalJson(wrappedPayload(selected)) : "No payload loaded";
  const match = Boolean(selected && verifiedHash && verifiedHash === selected.bytes32);

  return (
    <section id="verify" className="py-24 px-6 bg-[#0B0B0D]">
      <div className="max-w-6xl mx-auto">
        <div className="mb-12">
          <p className="text-[10px] font-mono tracking-widest uppercase text-[#E55A1C] mb-3">
            Verification panel
          </p>
          <h2
            className="text-4xl font-black text-[#F3F2EE]"
            style={{ fontFamily: "Sora, sans-serif" }}
          >
            Canonical JSON → SHA-256 → bytes32
          </h2>
          <p className="mt-3 text-[#8B8D91] max-w-2xl">
            Mantle stores the commitment. The payload stays public so outcomes can later be
            anchored without giving the contract custody or live trading authority.
          </p>
        </div>

        <div className="grid md:grid-cols-[1fr_360px] gap-6">
          {/* JSON panel */}
          <div className="rounded-[12px] border border-[rgba(243,242,238,0.08)] bg-[#0B0B0D] overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[rgba(243,242,238,0.06)] bg-[#1A1A1E]">
              <span className="text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider">
                Payload (canonical JSON)
              </span>
              <button
                onClick={() => copy(jsonStr, "json")}
                className="flex items-center gap-1.5 text-[10px] font-mono text-[#8B8D91] hover:text-[#F3F2EE] transition-colors"
              >
                <Copy className="size-3" />
                {copied === "json" ? "Copied!" : "Copy"}
              </button>
            </div>
            <pre className="p-5 text-[11px] font-mono text-[#8B8D91] overflow-auto max-h-80 leading-relaxed whitespace-pre-wrap break-all">
              {jsonStr}
            </pre>
          </div>

          {/* Hash panel */}
          <div className="rounded-[12px] border border-[rgba(243,242,238,0.08)] bg-[#1A1A1E] p-6 space-y-5 h-fit">
            {match && (
              <div className="flex items-center gap-2 text-emerald-400 text-xs font-mono bg-[rgba(52,211,153,0.08)] border border-[rgba(52,211,153,0.2)] rounded-[8px] px-3 py-2">
                <CheckCircle className="size-3.5 shrink-0" />
                Hash verified — on-chain match confirmed
              </div>
            )}

            <div>
              <span className="text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider block mb-2">
                Recomputed SHA-256
              </span>
              <div className="flex items-start gap-2">
                <code className="text-[11px] font-mono text-[#F3F2EE] break-all flex-1 leading-relaxed">
                  {verifiedHash || "pending..."}
                </code>
                {verifiedHash && (
                  <button
                    onClick={() => copy(verifiedHash, "hash")}
                    className="shrink-0 text-[#8B8D91] hover:text-[#F3F2EE] transition-colors"
                  >
                    <Copy className="size-3.5" />
                  </button>
                )}
              </div>
            </div>

            <div className="border-t border-[rgba(243,242,238,0.06)] pt-5">
              <span className="text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider block mb-2">
                Exported bytes32 (on-chain)
              </span>
              <code className="text-[11px] font-mono text-[#E55A1C] break-all leading-relaxed">
                {selected?.bytes32 || "pending..."}
              </code>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
