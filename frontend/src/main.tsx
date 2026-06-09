import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { createPublicClient, defineChain, getContract, http, type Hex } from "viem";
import "./styles.css";

type Commitment = {
  bytes32: Hex;
  kind: string;
  source: string;
  schema_version: string;
  hash_algorithm: string;
  payload: {
    row_id?: number;
    strategy?: string;
    question?: string;
    fair_prob?: number;
    avg_price?: number;
    confidence?: number;
    stake?: number;
    shares?: number;
    reason?: string;
    timestamp?: string;
    opened_at?: string;
    resolved?: number;
    won?: boolean | null;
    pnl?: number | null;
    // Equity fields
    ticker?: string;
    entry_price?: number;
    stop_loss?: number;
    take_profit?: number;
    status?: string;
    realized_pnl?: number | null;
  };
};

type RegistryEvent = {
  id: string;
  agentId: string;
  decisionHash: string;
  reporter: string;
  uri: string;
};

type PerformanceSummary = {
  generated_at: string;
  total_commitments: number;
  equity_trades: {
    total: number;
    closed: number;
    open: number;
    realized_pnl: number;
    win_rate: number;
    avg_confidence: number;
  };
  strategies: Array<{ name: string; count: number }>;
};

const registryAbi = [
  {
    type: "event",
    name: "DecisionRecorded",
    inputs: [
      { name: "id", type: "uint256", indexed: true },
      { name: "agentId", type: "bytes32", indexed: true },
      { name: "decisionHash", type: "bytes32", indexed: true },
      { name: "reporter", type: "address", indexed: false },
      { name: "uri", type: "string", indexed: false },
    ],
  },
  {
    type: "function",
    name: "decisionCount",
    stateMutability: "view",
    inputs: [],
    outputs: [{ type: "uint256" }],
  },
] as const;

const mantleSepolia = defineChain({
  id: 5003,
  name: "Mantle Sepolia",
  nativeCurrency: { decimals: 18, name: "MNT", symbol: "MNT" },
  rpcUrls: { default: { http: ["https://rpc.sepolia.mantle.xyz"] } },
  blockExplorers: { default: { name: "Mantle Explorer", url: "https://sepolia.mantlescan.xyz" } },
});

const registryAddress = import.meta.env.VITE_AGENT_REGISTRY_ADDRESS as Hex | undefined;
const rpcUrl = import.meta.env.VITE_MANTLE_RPC_URL as string | undefined;
const explorerBase = (import.meta.env.VITE_MANTLE_EXPLORER_BASE as string | undefined) || "https://sepolia.mantlescan.xyz";

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value as Record<string, unknown>)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return `0x${Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("")}`;
}

function wrappedPayload(commitment: Commitment) {
  return {
    kind: commitment.kind,
    payload: commitment.payload,
    schema_version: commitment.schema_version,
    source: commitment.source,
  };
}

function formatPct(value?: number) {
  if (typeof value !== "number") return "n/a";
  return `${Math.round(value * 1000) / 10}%`;
}

function shortHash(value: string) {
  return `${value.slice(0, 10)}...${value.slice(-8)}`;
}

function isEquityDecision(item: Commitment) {
  return Boolean(item.payload.ticker || item.payload.strategy === "equity_analyst");
}

function PolymarketCard({ item }: { item: Commitment }) {
  return (
    <article className="decision" key={item.bytes32}>
      <div>
        <h3>{item.payload.question}</h3>
        <p>{item.payload.reason}</p>
      </div>
      <dl>
        <dt>Strategy</dt><dd>{item.payload.strategy}</dd>
        <dt>Fair prob</dt><dd>{formatPct(item.payload.fair_prob)}</dd>
        <dt>Price</dt><dd>{item.payload.avg_price?.toFixed(4) ?? "n/a"}</dd>
        <dt>Confidence</dt><dd>{formatPct(item.payload.confidence)}</dd>
        <dt>Hash</dt><dd>{shortHash(item.bytes32)}</dd>
      </dl>
    </article>
  );
}

function EquityCard({ item }: { item: Commitment }) {
  const p = item.payload;
  const statusClass = p.status === "closed" ? "statusClosed" : p.status === "open" ? "statusOpen" : "";
  return (
    <article className="decision decisionEquity" key={item.bytes32}>
      <div>
        <div className="equityHeader">
          <span className="equityTicker">{p.ticker}</span>
          {p.status && <span className={`equityStatus ${statusClass}`}>{p.status}</span>}
        </div>
        <p>{p.reason}</p>
      </div>
      <dl>
        <dt>Strategy</dt><dd>{p.strategy}</dd>
        <dt>Confidence</dt><dd>{formatPct(p.confidence)}</dd>
        <dt>Entry</dt><dd>{p.entry_price != null ? `$${p.entry_price.toFixed(2)}` : "n/a"}</dd>
        <dt>Stop</dt><dd>{p.stop_loss != null ? `$${p.stop_loss.toFixed(2)}` : "n/a"}</dd>
        <dt>Target</dt><dd>{p.take_profit != null ? `$${p.take_profit.toFixed(2)}` : "n/a"}</dd>
        <dt>P&L</dt><dd>{p.realized_pnl != null ? `$${p.realized_pnl.toFixed(2)}` : p.pnl != null ? `$${p.pnl.toFixed(2)}` : "open"}</dd>
        <dt>Hash</dt><dd>{shortHash(item.bytes32)}</dd>
      </dl>
    </article>
  );
}

function DecisionCard({ item }: { item: Commitment }) {
  return isEquityDecision(item) ? <EquityCard item={item} /> : <PolymarketCard item={item} />;
}

// --- Performance Tab ---
function PerformanceTab({ commitments, perf }: { commitments: Commitment[]; perf: PerformanceSummary | null }) {
  const byDate = useMemo(() => {
    const groups: Record<string, number> = {};
    for (const item of commitments) {
      const ts = item.payload.timestamp || item.payload.opened_at;
      if (!ts) continue;
      const date = ts.slice(0, 10);
      groups[date] = (groups[date] || 0) + 1;
    }
    return Object.entries(groups).sort((a, b) => b[0].localeCompare(a[0]));
  }, [commitments]);

  if (!perf) {
    return (
      <div className="perfLoading">
        <p>Performance data loading...</p>
        <p className="muted">Ensure <code>performance_summary.json</code> is present in <code>/public</code>.</p>
      </div>
    );
  }

  const eq = perf.equity_trades;

  return (
    <div className="perfGrid">
      <div className="perfStats">
        <div className="perfStatCard">
          <strong>{perf.total_commitments}</strong>
          <span>Total decisions anchored</span>
        </div>
        <div className="perfStatCard">
          <strong>{eq.total}</strong>
          <span>Equity trades total</span>
        </div>
        <div className="perfStatCard">
          <strong className={eq.realized_pnl >= 0 ? "positive" : "negative"}>
            ${eq.realized_pnl.toFixed(2)}
          </strong>
          <span>Closed P&L</span>
        </div>
        <div className="perfStatCard">
          <strong>{formatPct(eq.win_rate)}</strong>
          <span>Win rate</span>
        </div>
        <div className="perfStatCard">
          <strong>{formatPct(eq.avg_confidence)}</strong>
          <span>Avg confidence</span>
        </div>
        <div className="perfStatCard">
          <strong>{eq.open}</strong>
          <span>Open positions</span>
        </div>
      </div>

      <div className="perfSection">
        <h3>Strategy breakdown</h3>
        <table className="stratTable">
          <thead>
            <tr>
              <th>Strategy</th>
              <th>Decisions</th>
            </tr>
          </thead>
          <tbody>
            {perf.strategies.map((s) => (
              <tr key={s.name}>
                <td>{s.name}</td>
                <td>{s.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="perfSection">
        <h3>Anchored decisions by date</h3>
        {byDate.length === 0 ? (
          <p className="muted">No dated commitments found.</p>
        ) : (
          <table className="stratTable">
            <thead>
              <tr>
                <th>Date</th>
                <th>Commitments</th>
              </tr>
            </thead>
            <tbody>
              {byDate.map(([date, count]) => (
                <tr key={date}>
                  <td>{date}</td>
                  <td>{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// --- Verify Tab ---
function VerifyTab({ selected, verifiedHash }: { selected: Commitment | undefined; verifiedHash: string }) {
  return (
    <section className="verify" id="verify">
      <div className="sectionHead">
        <p className="eyebrow">Verification panel</p>
        <h2>Canonical JSON to SHA-256 to bytes32</h2>
      </div>
      <div className="verifyGrid">
        <pre>{selected ? canonicalJson(wrappedPayload(selected)) : "No payload loaded"}</pre>
        <div className="hashBox">
          <span>Recomputed</span>
          <strong>{verifiedHash || "pending"}</strong>
          <span>Exported</span>
          <strong>{selected?.bytes32 || "pending"}</strong>
          <p>
            Mantle stores the commitment. The payload stays public and inspectable, so outcomes can later be anchored
            without giving the contract custody or live trading authority.
          </p>
        </div>
      </div>
    </section>
  );
}

// --- Decisions Tab ---
const PAGE_SIZE = 10;

function DecisionsTab({
  commitments,
  events,
  status,
  explorerLink,
  registryAddress,
  explorerBase,
}: {
  commitments: Commitment[];
  events: RegistryEvent[];
  status: string;
  explorerLink: string;
  registryAddress: Hex | undefined;
  explorerBase: string;
}) {
  const [search, setSearch] = useState("");
  const [showAll, setShowAll] = useState(false);

  const filtered = useMemo(() => {
    if (!search.trim()) return commitments;
    const q = search.trim().toLowerCase();
    return commitments.filter((item) => item.bytes32.toLowerCase().includes(q));
  }, [commitments, search]);

  const visible = showAll ? filtered : filtered.slice(0, PAGE_SIZE);
  const hasMore = filtered.length > PAGE_SIZE && !showAll;

  const fallbackEvents = commitments.map((item, index) => ({
    id: String(index),
    agentId: "fallback",
    decisionHash: item.bytes32,
    reporter: "not broadcast",
    uri: `sample#line-${index + 1}`,
  }));

  const displayEvents = events.length ? events : fallbackEvents;

  return (
    <section className="grid">
      <div className="panel">
        <div className="sectionHead">
          <p className="eyebrow">Decision feed</p>
          <h2>Auditable AI payloads</h2>
        </div>
        <div className="searchRow">
          <input
            className="hashSearch"
            type="text"
            placeholder="Filter by hash..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setShowAll(false); }}
          />
        </div>
        <div className="feed">
          {visible.length === 0 ? (
            <p className="muted">No decisions match that hash fragment.</p>
          ) : (
            visible.map((item) => <DecisionCard key={item.bytes32} item={item} />)
          )}
        </div>
        {hasMore && (
          <button className="showMore" onClick={() => setShowAll(true)}>
            Show all {filtered.length} decisions
          </button>
        )}
      </div>

      <aside className="panel" id="registry">
        <div className="sectionHead">
          <p className="eyebrow">Mantle registry</p>
          <h2>Reputation layer</h2>
        </div>
        <p className="status">{status}</p>
        <dl className="registryFacts">
          <dt>Contract</dt><dd>{registryAddress || "Set VITE_AGENT_REGISTRY_ADDRESS"}</dd>
          <dt>Explorer</dt><dd>{explorerLink ? <a href={explorerLink}>{explorerBase}</a> : "Pending deployment"}</dd>
          <dt>Events</dt><dd>{events.length ? `${events.length} live events` : "Using documented fallback JSON"}</dd>
        </dl>
        <div className="events">
          {displayEvents.map((event) => (
            <div className="event" key={`${event.id}-${event.decisionHash}`}>
              <strong>#{event.id} {shortHash(event.decisionHash)}</strong>
              <span>{event.uri}</span>
            </div>
          ))}
        </div>
      </aside>
    </section>
  );
}

type Tab = "decisions" | "performance" | "verify";

function App() {
  const [commitments, setCommitments] = useState<Commitment[]>([]);
  const [events, setEvents] = useState<RegistryEvent[]>([]);
  const [verifiedHash, setVerifiedHash] = useState<string>("");
  const [status, setStatus] = useState("Loading exported decision payloads");
  const [perf, setPerf] = useState<PerformanceSummary | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("decisions");

  const selected = commitments[0];

  useEffect(() => {
    fetch("/mantle_commitments.sample.json")
      .then((response) => response.json())
      .then((data: Commitment[]) => {
        setCommitments(data);
        setStatus("Static exported payloads loaded. Add Mantle env vars for live registry events.");
      })
      .catch(() => setStatus("Could not load fallback commitment data."));
  }, []);

  useEffect(() => {
    fetch("/performance_summary.json")
      .then((r) => r.json())
      .then((data: PerformanceSummary) => setPerf(data))
      .catch(() => setPerf(null));
  }, []);

  useEffect(() => {
    if (!rpcUrl || !registryAddress) return;

    const client = createPublicClient({ chain: mantleSepolia, transport: http(rpcUrl) });
    const contract = getContract({ address: registryAddress, abi: registryAbi, client });

    contract
      .getEvents
      .DecisionRecorded()
      .then((logs) => {
        setEvents(
          logs.slice(-8).reverse().map((log) => ({
            id: String(log.args.id ?? ""),
            agentId: String(log.args.agentId ?? ""),
            decisionHash: String(log.args.decisionHash ?? ""),
            reporter: String(log.args.reporter ?? ""),
            uri: String(log.args.uri ?? ""),
          }))
        );
        setStatus("Live Mantle registry events loaded.");
      })
      .catch(() => setStatus("Mantle RPC configured, but registry events could not be loaded."));
  }, []);

  useEffect(() => {
    if (!selected) return;
    sha256Hex(canonicalJson(wrappedPayload(selected))).then(setVerifiedHash);
  }, [selected]);

  const stats = useMemo(() => {
    const anchored = events.length || commitments.length;
    const resolved = commitments.filter((item) => item.payload.resolved).length;
    const pnl = commitments.reduce((total, item) => total + (item.payload.pnl ?? 0), 0);
    const avgConfidence =
      commitments.length === 0
        ? 0
        : commitments.reduce((total, item) => total + (item.payload.confidence ?? 0), 0) / commitments.length;
    return { anchored, resolved, pnl, avgConfidence };
  }, [commitments, events]);

  const explorerLink = registryAddress ? `${explorerBase.replace(/\/$/, "")}/address/${registryAddress}` : "";

  return (
    <main>
      <section className="hero">
        <div className="heroCopy">
          <p className="eyebrow">AI Alpha &amp; Data / Mantle deployment benchmark</p>
          <h1>Mantle-Verifiable AI Prediction Agent</h1>
          <p className="pitch">
            AI market decisions become deterministic public payloads, `bytes32` commitments, and Mantle registry events
            that judges can independently verify.
          </p>
          <div className="actions">
            <a className="primary" href={explorerLink || "#registry"}>View on Mantle Explorer</a>
            <a className="secondary" href="#verify">Recompute hash</a>
          </div>
        </div>
        <div className="registryVisual" aria-label="Mantle registry flow">
          <div>Bot</div>
          <span />
          <div>JSONL</div>
          <span />
          <div>bytes32</div>
          <span />
          <div>Mantle</div>
        </div>
      </section>

      <section className="stats" aria-label="Agent stats">
        <div><strong>{stats.anchored}</strong><span>decisions ready or anchored</span></div>
        <div><strong>{stats.resolved}</strong><span>resolved outcomes</span></div>
        <div><strong>${stats.pnl.toFixed(2)}</strong><span>paper ROI PnL</span></div>
        <div><strong>{formatPct(stats.avgConfidence)}</strong><span>avg confidence</span></div>
      </section>

      <nav className="tabs" aria-label="Main navigation">
        <button
          className={`tab${activeTab === "decisions" ? " tabActive" : ""}`}
          onClick={() => setActiveTab("decisions")}
        >
          Decisions
        </button>
        <button
          className={`tab${activeTab === "performance" ? " tabActive" : ""}`}
          onClick={() => setActiveTab("performance")}
        >
          Performance
        </button>
        <button
          className={`tab${activeTab === "verify" ? " tabActive" : ""}`}
          onClick={() => setActiveTab("verify")}
        >
          Verify
        </button>
      </nav>

      <div className="tabContent">
        {activeTab === "decisions" && (
          <DecisionsTab
            commitments={commitments}
            events={events}
            status={status}
            explorerLink={explorerLink}
            registryAddress={registryAddress}
            explorerBase={explorerBase}
          />
        )}
        {activeTab === "performance" && (
          <section className="perfSection padded">
            <div className="sectionHead">
              <p className="eyebrow">Performance summary</p>
              <h2>AI trading track record</h2>
            </div>
            <PerformanceTab commitments={commitments} perf={perf} />
          </section>
        )}
        {activeTab === "verify" && (
          <VerifyTab selected={selected} verifiedHash={verifiedHash} />
        )}
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
