import { createPublicClient, defineChain, getContract, http, type Hex } from "viem";

export const registryAbi = [
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

export const mantleSepolia = defineChain({
  id: 5003,
  name: "Mantle Sepolia",
  nativeCurrency: { decimals: 18, name: "MNT", symbol: "MNT" },
  rpcUrls: { default: { http: ["https://rpc.sepolia.mantle.xyz"] } },
  blockExplorers: {
    default: { name: "Mantle Explorer", url: "https://sepolia.mantlescan.xyz" },
  },
});

export const registryAddress = import.meta.env.VITE_AGENT_REGISTRY_ADDRESS as Hex | undefined;
export const rpcUrl = import.meta.env.VITE_MANTLE_RPC_URL as string | undefined;
export const explorerBase =
  (import.meta.env.VITE_MANTLE_EXPLORER_BASE as string | undefined) ||
  "https://sepolia.mantlescan.xyz";

export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value as Record<string, unknown>)
      .sort()
      .map((k) => `${JSON.stringify(k)}:${canonicalJson((value as Record<string, unknown>)[k])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

export async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return `0x${Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")}`;
}

export function shortHash(value: string) {
  return `${value.slice(0, 10)}...${value.slice(-8)}`;
}

export function formatPct(value?: number) {
  if (typeof value !== "number") return "n/a";
  return `${Math.round(value * 1000) / 10}%`;
}

export function createMantleClient(url: string) {
  return createPublicClient({ chain: mantleSepolia, transport: http(url) });
}

export function createRegistryContract(address: Hex, client: ReturnType<typeof createMantleClient>) {
  return getContract({ address, abi: registryAbi, client });
}
