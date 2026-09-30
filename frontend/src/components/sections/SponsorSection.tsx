import { ArrowUpRight } from "lucide-react";

const sponsorMailto =
  "mailto:nikolas@helpmarq.com?subject=SAC%20Capital%20sponsorship%20placement";

export function SponsorSection() {
  return (
    <section className="border-t border-[rgba(243,242,238,0.06)] bg-[#0B0B0D] px-6 py-20 md:py-24">
      <div
        className="mx-auto grid max-w-7xl gap-8 border-y border-[rgba(243,242,238,0.1)] py-10 md:grid-cols-[1fr_auto] md:items-end md:py-12"
        style={{ fontFamily: "Geist, sans-serif" }}
      >
        <div>
          <p className="mb-5 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#006bff]">
            Partner with the project
          </p>
          <h2 className="max-w-3xl text-3xl font-semibold leading-tight tracking-[-0.03em] text-[#F3F2EE] sm:text-4xl md:text-5xl">
            Sponsorship &amp; Ad Placements
          </h2>
          <p className="mt-5 max-w-2xl text-base leading-relaxed text-[#8B8D91] md:text-lg">
            We’re accepting sponsorship placements and site ad space to help fund continued development.
          </p>
        </div>

        <a
          href={sponsorMailto}
          className="group inline-flex w-fit items-center gap-3 border-b border-[#006bff] pb-2 text-sm font-semibold text-[#F3F2EE] transition-colors hover:text-[#006bff] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#006bff] focus-visible:ring-offset-4 focus-visible:ring-offset-[#0B0B0D]"
        >
          Discuss a placement
          <ArrowUpRight className="size-4 transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" aria-hidden="true" />
        </a>
      </div>
    </section>
  );
}
