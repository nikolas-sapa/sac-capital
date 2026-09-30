import { useEffect, useRef, useState } from "react";
import { Activity, ChevronDown, Clock3, ScanSearch, X } from "lucide-react";

type RunStatus = "running" | "completed" | "failed" | "unknown";

type StatusEvent = {
  run_id: string;
  run_type: "routine" | "full_scan";
  status: RunStatus;
  started_at: string;
  updated_at: string;
};

type BotStatusDocument = {
  version: 1;
  latest_activity: StatusEvent;
  latest_full_scan: StatusEvent;
};

const exactTimeFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Athens",
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
  timeZoneName: "short",
});

function isStatusDocument(value: unknown): value is BotStatusDocument {
  if (!value || typeof value !== "object") return false;
  const document = value as Partial<BotStatusDocument>;
  const isEvent = (event: StatusEvent | undefined) =>
    Boolean(
      event &&
        typeof event.started_at === "string" &&
        Number.isFinite(Date.parse(event.started_at)) &&
        ["running", "completed", "failed", "unknown"].includes(event.status),
    );

  return document.version === 1 && isEvent(document.latest_activity) && isEvent(document.latest_full_scan);
}

function relativeAge(timestamp: string, now: number) {
  const elapsedMinutes = Math.max(0, Math.floor((now - Date.parse(timestamp)) / 60_000));
  if (elapsedMinutes < 1) return "just now";
  if (elapsedMinutes < 60) return `${elapsedMinutes} minute${elapsedMinutes === 1 ? "" : "s"}`;

  const hours = Math.floor(elapsedMinutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"}`;

  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"}`;
}

function agePhrase(timestamp: string, now: number) {
  const age = relativeAge(timestamp, now);
  return age === "just now" ? age : `${age} ago`;
}

function exactTime(timestamp: string) {
  return exactTimeFormatter.format(new Date(timestamp));
}

export function BotStatusBanner() {
  const [status, setStatus] = useState<BotStatusDocument | null>(null);
  const [isHistorical, setIsHistorical] = useState(true);
  const [isUnavailable, setIsUnavailable] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const containerRef = useRef<HTMLElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let active = true;
    let liveApplied = false;
    let seedFailed = false;
    let liveFailed = false;

    function updateUnavailableState() {
      if (active && seedFailed && liveFailed) setIsUnavailable(true);
    }

    async function readStatus(url: string) {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) throw new Error(`Status request failed (${response.status})`);
      const value: unknown = await response.json();
      if (!isStatusDocument(value)) throw new Error("Invalid status response");
      return value;
    }

    readStatus("/bot-status-seed.json")
      .then((seed) => {
        if (active && !liveApplied) setStatus(seed);
      })
      .catch(() => {
        seedFailed = true;
        updateUnavailableState();
      });

    readStatus("/api/bot-status")
      .then((live) => {
        if (!active) return;
        liveApplied = true;
        setStatus(live);
        setIsHistorical(false);
      })
      .catch(() => {
        if (active) setIsHistorical(true);
        liveFailed = true;
        updateUnavailableState();
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (isOpen) closeButtonRef.current?.focus();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;

    function handlePointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !containerRef.current?.contains(event.target)) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsOpen(false);
        triggerRef.current?.focus();
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  function closePopup() {
    setIsOpen(false);
    triggerRef.current?.focus();
  }

  return (
    <section
      ref={containerRef}
      aria-label="Bot run status"
      className="relative z-40 bg-[#0B0B0D] px-6 pb-3 pt-24"
      style={{ fontFamily: "Geist, sans-serif" }}
    >
      <div className="relative mx-auto max-w-7xl">
        <button
          ref={triggerRef}
          type="button"
          aria-haspopup="dialog"
          aria-expanded={isOpen}
          aria-controls="bot-activity-popup"
          onClick={() => setIsOpen((open) => !open)}
          className="group inline-flex max-w-full items-center gap-2.5 rounded-full border border-[rgba(243,242,238,0.12)] bg-[#101013] px-4 py-2.5 text-left text-sm text-[#F3F2EE] transition-colors hover:border-[rgba(0,107,255,0.65)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#006bff] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0B0B0D]"
        >
          <Activity className="size-4 shrink-0 text-[#006bff]" strokeWidth={1.75} aria-hidden="true" />
          <span className="truncate">
            {status
              ? `The bot last ran ${agePhrase(status.latest_activity.started_at, now)}`
              : isUnavailable
                ? "The bot run time is unavailable"
                : "Loading bot run history…"}
          </span>
          {isHistorical && status && <span className="sr-only">Historical data</span>}
          <ChevronDown className={`size-4 shrink-0 text-[#8B8D91] transition-transform ${isOpen ? "rotate-180" : ""}`} aria-hidden="true" />
        </button>

        {isOpen && (
          <div
            id="bot-activity-popup"
            role="dialog"
            aria-label="Bot activity details"
            className="absolute left-0 top-[calc(100%+0.75rem)] z-50 w-[min(26rem,calc(100vw-3rem))] rounded-2xl border border-[rgba(243,242,238,0.12)] bg-[#101013] p-5 shadow-[0_20px_60px_rgba(0,0,0,0.55)] sm:p-6"
          >
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#006bff]">Bot activity</p>
                <h2 className="mt-1 text-lg font-semibold text-[#F3F2EE]">Run history</h2>
              </div>
              <button
                ref={closeButtonRef}
                type="button"
                onClick={closePopup}
                aria-label="Close bot activity details"
                className="rounded-full p-1.5 text-[#8B8D91] hover:bg-[rgba(243,242,238,0.08)] hover:text-[#F3F2EE] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#006bff]"
              >
                <X className="size-4" aria-hidden="true" />
              </button>
            </div>

            {isHistorical && status && (
              <p className="mb-4 rounded-lg border border-[rgba(243,242,238,0.08)] bg-[rgba(243,242,238,0.03)] px-3 py-2 text-xs text-[#AEB0B4]">
                Showing historical status. Live run feed is unavailable.
              </p>
            )}
            {isUnavailable && (
              <p className="mb-4 rounded-lg border border-[rgba(243,242,238,0.08)] bg-[rgba(243,242,238,0.03)] px-3 py-2 text-xs text-[#AEB0B4]">
                Run history is unavailable right now.
              </p>
            )}

            <div className="space-y-5">
              <div className="flex gap-3">
                <Activity className="mt-0.5 size-4 shrink-0 text-[#006bff]" strokeWidth={1.75} aria-hidden="true" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-[#F3F2EE]">
                    {status ? `The bot last ran ${agePhrase(status.latest_activity.started_at, now)}` : "Latest run time unavailable"}
                  </p>
                  <p className="mt-1 flex items-center gap-1.5 text-xs tabular-nums text-[#8B8D91]">
                    <Clock3 className="size-3" strokeWidth={1.75} aria-hidden="true" />
                    {status ? exactTime(status.latest_activity.started_at) : "Exact run time unavailable"}
                  </p>
                  {status?.latest_activity.status === "failed" && (
                    <p className="mt-1.5 text-xs text-[#AEB0B4]">Most recent run ended with an error.</p>
                  )}
                  {status?.latest_activity.status === "running" && (
                    <p className="mt-1.5 text-xs text-[#AEB0B4]">Most recent run is marked as in progress.</p>
                  )}
                </div>
              </div>

              <div className="border-t border-[rgba(243,242,238,0.08)] pt-4">
                <div className="flex gap-3">
                  <ScanSearch className="mt-0.5 size-4 shrink-0 text-[#006bff]" strokeWidth={1.75} aria-hidden="true" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-[#F3F2EE]">
                      {status ? `Latest full scan ${agePhrase(status.latest_full_scan.started_at, now)}` : "Latest full scan time unavailable"}
                    </p>
                    <p className="mt-1 text-xs tabular-nums text-[#8B8D91]">
                      {status ? exactTime(status.latest_full_scan.started_at) : "Exact scan time unavailable"}
                    </p>
                    {status?.latest_full_scan.status === "unknown" && (
                      <p className="mt-1.5 text-xs text-[#AEB0B4]">Historical outcome is unknown.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
