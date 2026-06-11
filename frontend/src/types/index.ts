import type { Hex } from "viem";

export type Commitment = {
  bytes32: Hex;
  canonical_json: string;
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
    ticker?: string;
    entry_price?: number;
    stop_loss?: number;
    take_profit?: number;
    status?: string;
    realized_pnl?: number | null;
  };
};

export type RegistryEvent = {
  id: string;
  agentId: string;
  decisionHash: string;
  reporter: string;
  uri: string;
};

export type EquityPosition = {
  id: string;
  ticker: string;
  side: string;
  status: "open" | "closed" | "submitted" | string;
  shares: number | null;
  entry_price: number | null;
  mark_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number | null;
  exit_price: number | null;
  exit_reason: string | null;
  confidence: number | null;
  strategy: string;
  mode: string;
  opened_at: string;
  closed_at: string | null;
};

export type PortfolioHistoryPoint = { label: string; value: number };
export type PortfolioHistory = { points: PortfolioHistoryPoint[]; base_value?: number };

export type PerformanceSummary = {
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
