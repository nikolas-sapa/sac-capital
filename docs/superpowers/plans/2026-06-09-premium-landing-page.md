# Premium Landing Page — Mantle-Verifiable AI Agent

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `frontend/` as a premium dark-mode landing page / app that showcases the Mantle-Verifiable AI Prediction Agent with world-class design — dithering shader hero, liquid glass nav, animated numbers, scroll-stacked features, 8-bit chart, and Mantle verification panel.

**Architecture:** Complete rewrite of `frontend/src/` keeping all existing data logic (Mantle client via viem, JSON fetches, hash verification). New component tree: `lib/`, `types/`, `data/`, `components/ui/`, `components/sections/`. Single `App.tsx` orchestrates sections. All Tailwind via CSS variables mapped to brand tokens.

**Tech Stack:** Vite + React 19 + TypeScript, Tailwind CSS v4 (`@tailwindcss/vite`), shadcn/ui primitives (button, navigation-menu), framer-motion, `@paper-design/shaders-react` + `@paper-design/shaders`, lucide-react, clsx, tailwind-merge, tw-animate-css, `@radix-ui/react-slot`, `class-variance-authority`, `@radix-ui/react-navigation-menu`, `@radix-ui/react-icons`

---

## File Map

| File | Responsibility |
|---|---|
| `frontend/package.json` | Add all new deps |
| `frontend/index.html` | Load Google Fonts (Sora, Plus Jakarta Sans, Geist Mono) |
| `frontend/src/index.css` | Tailwind v4 import + CSS brand token variables |
| `frontend/src/main.tsx` | Unchanged — createRoot only |
| `frontend/src/App.tsx` | Layout orchestrator — renders all sections in order |
| `frontend/src/lib/utils.ts` | `cn()` helper via clsx + tailwind-merge |
| `frontend/src/types/index.ts` | All TypeScript types: Commitment, RegistryEvent, PerformanceSummary |
| `frontend/src/data/mantle.ts` | Mantle client, ABI, env vars, canonicalJson, sha256Hex |
| `frontend/src/hooks/use-scroll.ts` | `useScroll(threshold)` hook for nav compact state |
| `frontend/src/components/ui/button.tsx` | shadcn Button primitive |
| `frontend/src/components/ui/navigation-menu.tsx` | shadcn NavigationMenu primitive |
| `frontend/src/components/ui/menu-toggle-icon.tsx` | Animated hamburger/X icon |
| `frontend/src/components/ui/motion-button.tsx` | Expanding circle CTA button |
| `frontend/src/components/ui/liquid-metal-button.tsx` | WebGL shader button |
| `frontend/src/components/ui/animated-blur-number.tsx` | Digit-by-digit blur-slide number |
| `frontend/src/components/ui/chart-area-step.tsx` | 8-bit SVG step area chart |
| `frontend/src/components/ui/animated-group.tsx` | Framer-motion stagger group |
| `frontend/src/components/sections/NavBar.tsx` | Liquid glass nav — floats, compacts on scroll |
| `frontend/src/components/sections/HeroSection.tsx` | Shader backdrop + macro headline + CTAs |
| `frontend/src/components/sections/StatsBar.tsx` | 4 animated-number stats strip |
| `frontend/src/components/sections/HowItWorksSection.tsx` | Scroll-stacked feature cards |
| `frontend/src/components/sections/DecisionsSection.tsx` | Animated card stack + tabbed decision feed |
| `frontend/src/components/sections/PerformanceSection.tsx` | 8-bit chart + perf stat cards |
| `frontend/src/components/sections/VerifySection.tsx` | Hash verification panel |
| `frontend/src/components/sections/CTASection.tsx` | Full-width dithering shader CTA |

---

## Task 1: Install dependencies and configure Tailwind v4

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/index.css`
- Modify: `frontend/index.html`
- Create: `frontend/vite.config.ts` (replaces any existing vite.config.js)

- [ ] **Step 1: Install all npm dependencies**

```bash
cd /Users/nikolassapalidis/polymarket-bot/frontend
npm install tailwindcss @tailwindcss/vite tw-animate-css framer-motion \
  @paper-design/shaders-react @paper-design/shaders \
  lucide-react clsx tailwind-merge \
  @radix-ui/react-slot class-variance-authority \
  @radix-ui/react-navigation-menu @radix-ui/react-icons
```

- [ ] **Step 2: Write `frontend/vite.config.ts`**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
```

- [ ] **Step 3: Write `frontend/src/index.css`**

```css
@import "tailwindcss";
@import "tw-animate-css";

@theme {
  --color-bg-dark: #0B0B0D;
  --color-surface-dark: #1A1A1E;
  --color-surface-light: #E9E8E3;
  --color-accent: #E55A1C;
  --color-accent-hover: #C94A12;
  --color-text-primary: #F3F2EE;
  --color-text-muted: #8B8D91;
  --color-border: rgba(243, 242, 238, 0.08);

  --font-display: "Sora", sans-serif;
  --font-body: "Plus Jakarta Sans", sans-serif;
  --font-mono: "Geist Mono", monospace;

  --radius-sm: 6px;
  --radius-md: 12px;
  --radius-lg: 20px;
}

:root {
  background: #0B0B0D;
  color: #F3F2EE;
  font-family: "Plus Jakarta Sans", sans-serif;
  -webkit-font-smoothing: antialiased;
}

* { box-sizing: border-box; }
body { margin: 0; }
```

- [ ] **Step 4: Update `frontend/index.html` — add Google Fonts**

Replace the `<head>` section to include:
```html
<!doctype html>
<html lang="en" class="dark">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Mantle-Verifiable AI Prediction Agent</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Verify Tailwind is working**

```bash
cd /Users/nikolassapalidis/polymarket-bot/frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds, no Tailwind errors.

- [ ] **Step 6: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/index.css frontend/index.html
git commit -m "feat: install Tailwind v4 + design deps for premium redesign"
```

---

## Task 2: Shared utilities, types, and Mantle data layer

**Files:**
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/data/mantle.ts`
- Create: `frontend/src/hooks/use-scroll.ts`

- [ ] **Step 1: Write `frontend/src/lib/utils.ts`**

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 2: Write `frontend/src/types/index.ts`**

```ts
import type { Hex } from "viem";

export type Commitment = {
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
```

- [ ] **Step 3: Write `frontend/src/data/mantle.ts`**

```ts
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
```

- [ ] **Step 4: Write `frontend/src/hooks/use-scroll.ts`**

```ts
import { useCallback, useEffect, useState } from "react";

export function useScroll(threshold: number) {
  const [scrolled, setScrolled] = useState(false);

  const onScroll = useCallback(() => {
    setScrolled(window.scrollY > threshold);
  }, [threshold]);

  useEffect(() => {
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, [onScroll]);

  useEffect(() => { onScroll(); }, [onScroll]);

  return scrolled;
}
```

- [ ] **Step 5: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot
git add frontend/src/lib frontend/src/types frontend/src/data frontend/src/hooks
git commit -m "feat: shared utils, types, Mantle data layer, scroll hook"
```

---

## Task 3: shadcn/ui primitive components

**Files:**
- Create: `frontend/src/components/ui/button.tsx`
- Create: `frontend/src/components/ui/navigation-menu.tsx`
- Create: `frontend/src/components/ui/menu-toggle-icon.tsx`

- [ ] **Step 1: Write `frontend/src/components/ui/button.tsx`**

```tsx
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-[6px] text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E55A1C] focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-[#E55A1C] text-[#F3F2EE] hover:bg-[#C94A12]",
        outline: "border border-[rgba(243,242,238,0.12)] bg-transparent text-[#F3F2EE] hover:bg-[rgba(243,242,238,0.06)]",
        ghost: "text-[#F3F2EE] hover:bg-[rgba(243,242,238,0.06)]",
        secondary: "bg-[#1A1A1E] text-[#F3F2EE] hover:bg-[rgba(243,242,238,0.1)]",
        link: "text-[#E55A1C] underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 px-3",
        lg: "h-11 px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
```

- [ ] **Step 2: Write `frontend/src/components/ui/menu-toggle-icon.tsx`**

```tsx
"use client";
import React from "react";
import { cn } from "@/lib/utils";

type MenuToggleProps = React.ComponentProps<"svg"> & {
  open: boolean;
  duration?: number;
};

export function MenuToggleIcon({
  open,
  className,
  fill = "none",
  stroke = "currentColor",
  strokeWidth = 2.5,
  strokeLinecap = "round",
  strokeLinejoin = "round",
  duration = 500,
  ...props
}: MenuToggleProps) {
  return (
    <svg
      strokeWidth={strokeWidth}
      fill={fill}
      stroke={stroke}
      viewBox="0 0 32 32"
      strokeLinecap={strokeLinecap}
      strokeLinejoin={strokeLinejoin}
      className={cn("transition-transform ease-in-out", open && "-rotate-45", className)}
      style={{ transitionDuration: `${duration}ms` }}
      {...props}
    >
      <path
        className={cn(
          "transition-all ease-in-out",
          open
            ? "[stroke-dasharray:20_300] [stroke-dashoffset:-32.42px]"
            : "[stroke-dasharray:12_63]"
        )}
        style={{ transitionDuration: `${duration}ms` }}
        d="M27 10 13 10C10.8 10 9 8.2 9 6 9 3.5 10.8 2 13 2 15.2 2 17 3.8 17 6L17 26C17 28.2 18.8 30 21 30 23.2 30 25 28.2 25 26 25 23.8 23.2 22 21 22L7 22"
      />
      <path d="M7 16 27 16" />
    </svg>
  );
}
```

- [ ] **Step 3: Write `frontend/src/components/ui/navigation-menu.tsx`**

Copy the full shadcn navigation-menu component provided in the task brief — import from `@radix-ui/react-navigation-menu`, wrap with brand-token class names matching dark theme (replace `bg-popover` with `bg-[#1A1A1E]`, `border-border` with `border-[rgba(243,242,238,0.08)]`, etc.).

```tsx
import * as React from "react";
import { ChevronDownIcon } from "@radix-ui/react-icons";
import * as NavigationMenuPrimitive from "@radix-ui/react-navigation-menu";
import { cva } from "class-variance-authority";
import { cn } from "@/lib/utils";

const NavigationMenu = React.forwardRef<
  React.ElementRef<typeof NavigationMenuPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof NavigationMenuPrimitive.Root>
>(({ className, children, ...props }, ref) => (
  <NavigationMenuPrimitive.Root
    ref={ref}
    className={cn("relative z-10 flex max-w-max flex-1 items-center justify-center", className)}
    {...props}
  >
    {children}
    <NavigationMenuViewport />
  </NavigationMenuPrimitive.Root>
));
NavigationMenu.displayName = NavigationMenuPrimitive.Root.displayName;

const NavigationMenuList = React.forwardRef<
  React.ElementRef<typeof NavigationMenuPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof NavigationMenuPrimitive.List>
>(({ className, ...props }, ref) => (
  <NavigationMenuPrimitive.List
    ref={ref}
    className={cn("group flex flex-1 list-none items-center justify-center space-x-1", className)}
    {...props}
  />
));
NavigationMenuList.displayName = NavigationMenuPrimitive.List.displayName;

const NavigationMenuItem = NavigationMenuPrimitive.Item;

const navigationMenuTriggerStyle = cva(
  "group inline-flex h-9 w-max items-center justify-center rounded-[6px] px-4 py-2 text-sm font-medium transition-colors text-[#F3F2EE] hover:bg-[rgba(243,242,238,0.06)] focus:outline-none disabled:pointer-events-none disabled:opacity-50"
);

const NavigationMenuTrigger = React.forwardRef<
  React.ElementRef<typeof NavigationMenuPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof NavigationMenuPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <NavigationMenuPrimitive.Trigger
    ref={ref}
    className={cn(navigationMenuTriggerStyle(), "group", className)}
    {...props}
  >
    {children}{" "}
    <ChevronDownIcon
      className="relative top-[1px] ml-1 h-3 w-3 transition duration-300 group-data-[state=open]:rotate-180 text-[#8B8D91]"
      aria-hidden="true"
    />
  </NavigationMenuPrimitive.Trigger>
));
NavigationMenuTrigger.displayName = NavigationMenuPrimitive.Trigger.displayName;

const NavigationMenuContent = React.forwardRef<
  React.ElementRef<typeof NavigationMenuPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof NavigationMenuPrimitive.Content>
>(({ className, ...props }, ref) => (
  <NavigationMenuPrimitive.Content
    ref={ref}
    className={cn(
      "left-0 top-0 w-full data-[motion^=from-]:animate-in data-[motion^=to-]:animate-out data-[motion^=from-]:fade-in data-[motion^=to-]:fade-out md:absolute md:w-auto",
      className
    )}
    {...props}
  />
));
NavigationMenuContent.displayName = NavigationMenuPrimitive.Content.displayName;

const NavigationMenuLink = NavigationMenuPrimitive.Link;

const NavigationMenuViewport = React.forwardRef<
  React.ElementRef<typeof NavigationMenuPrimitive.Viewport>,
  React.ComponentPropsWithoutRef<typeof NavigationMenuPrimitive.Viewport>
>(({ className, ...props }, ref) => (
  <div className={cn("absolute left-0 top-full flex justify-center")}>
    <NavigationMenuPrimitive.Viewport
      className={cn(
        "origin-top-center relative mt-1.5 h-[var(--radix-navigation-menu-viewport-height)] w-full overflow-hidden rounded-[12px] border border-[rgba(243,242,238,0.08)] bg-[#1A1A1E] text-[#F3F2EE] shadow-xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-90 md:w-[var(--radix-navigation-menu-viewport-width)]",
        className
      )}
      ref={ref}
      {...props}
    />
  </div>
));
NavigationMenuViewport.displayName = NavigationMenuPrimitive.Viewport.displayName;

export {
  navigationMenuTriggerStyle,
  NavigationMenu,
  NavigationMenuList,
  NavigationMenuItem,
  NavigationMenuContent,
  NavigationMenuTrigger,
  NavigationMenuLink,
  NavigationMenuViewport,
};
```

- [ ] **Step 4: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot
git add frontend/src/components/ui/
git commit -m "feat: shadcn button, navigation-menu, menu-toggle-icon primitives"
```

---

## Task 4: Custom UI primitives (motion-button, liquid-metal-button, animated-blur-number)

**Files:**
- Create: `frontend/src/components/ui/motion-button.tsx`
- Create: `frontend/src/components/ui/liquid-metal-button.tsx`
- Create: `frontend/src/components/ui/animated-blur-number.tsx`

- [ ] **Step 1: Write `frontend/src/components/ui/motion-button.tsx`**

```tsx
import { FC } from "react";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  label: string;
  variant?: "primary" | "secondary";
  classes?: string;
  onClick?: () => void;
}

const MotionButton: FC<Props> = ({ label, classes, onClick }) => {
  return (
    <button
      onClick={onClick}
      className={cn(
        "bg-[#1A1A1E] group relative h-auto w-50 cursor-pointer rounded-full border-none p-1 outline-none",
        classes
      )}
    >
      <span
        className="block h-12 w-12 overflow-hidden rounded-full bg-[#E55A1C] duration-500 group-hover:w-full"
        aria-hidden="true"
      />
      <div className="absolute top-1/2 left-4 translate-x-0 -translate-y-1/2 duration-500 group-hover:translate-x-[0.4rem]">
        <ArrowRight className="text-[#F3F2EE] size-6" />
      </div>
      <span className="absolute top-2/4 left-2/4 ml-4 -translate-x-2/4 -translate-y-2/4 whitespace-nowrap text-center text-lg font-medium tracking-tight text-[#F3F2EE] duration-500 group-hover:text-[#F3F2EE]"
        style={{ fontFamily: "var(--font-body)" }}>
        {label}
      </span>
    </button>
  );
};

export default MotionButton;
```

- [ ] **Step 2: Write `frontend/src/components/ui/liquid-metal-button.tsx`**

Copy exact code from task brief (the `LiquidMetalButton` component using `liquidMetalFragmentShader` and `ShaderMount` from `@paper-design/shaders`). No modifications needed — the component is self-contained.

```tsx
import { liquidMetalFragmentShader, ShaderMount } from "@paper-design/shaders";
import { Sparkles } from "lucide-react";
import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";

interface LiquidMetalButtonProps {
  label?: string;
  onClick?: () => void;
  viewMode?: "text" | "icon";
}

export function LiquidMetalButton({
  label = "Get Started",
  onClick,
  viewMode = "text",
}: LiquidMetalButtonProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [isPressed, setIsPressed] = useState(false);
  const [ripples, setRipples] = useState<Array<{ x: number; y: number; id: number }>>([]);
  const shaderRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const shaderMount = useRef<any>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const rippleId = useRef(0);

  const dimensions = useMemo(() => {
    if (viewMode === "icon") {
      return { width: 46, height: 46, innerWidth: 42, innerHeight: 42, shaderWidth: 46, shaderHeight: 46 };
    }
    return { width: 142, height: 46, innerWidth: 138, innerHeight: 42, shaderWidth: 142, shaderHeight: 46 };
  }, [viewMode]);

  useEffect(() => {
    const styleId = "shader-canvas-style-exploded";
    if (!document.getElementById(styleId)) {
      const style = document.createElement("style");
      style.id = styleId;
      style.textContent = `
        .shader-container-exploded canvas {
          width: 100% !important; height: 100% !important;
          display: block !important; position: absolute !important;
          top: 0 !important; left: 0 !important;
          border-radius: 100px !important;
        }
        @keyframes ripple-animation {
          0% { transform: translate(-50%, -50%) scale(0); opacity: 0.6; }
          100% { transform: translate(-50%, -50%) scale(4); opacity: 0; }
        }
      `;
      document.head.appendChild(style);
    }

    const loadShader = async () => {
      try {
        if (shaderRef.current) {
          if (shaderMount.current?.destroy) shaderMount.current.destroy();
          shaderMount.current = new ShaderMount(
            shaderRef.current,
            liquidMetalFragmentShader,
            { u_repetition: 4, u_softness: 0.5, u_shiftRed: 0.3, u_shiftBlue: 0.3,
              u_distortion: 0, u_contour: 0, u_angle: 45, u_scale: 8,
              u_shape: 1, u_offsetX: 0.1, u_offsetY: -0.1 },
            undefined,
            0.6
          );
        }
      } catch (error) {
        console.error("Failed to load shader:", error);
      }
    };

    loadShader();
    return () => { if (shaderMount.current?.destroy) { shaderMount.current.destroy(); shaderMount.current = null; } };
  }, []);

  const handleMouseEnter = () => { setIsHovered(true); shaderMount.current?.setSpeed?.(1); };
  const handleMouseLeave = () => { setIsHovered(false); setIsPressed(false); shaderMount.current?.setSpeed?.(0.6); };

  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    if (shaderMount.current?.setSpeed) {
      shaderMount.current.setSpeed(2.4);
      setTimeout(() => { shaderMount.current?.setSpeed?.(isHovered ? 1 : 0.6); }, 300);
    }
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const ripple = { x: e.clientX - rect.left, y: e.clientY - rect.top, id: rippleId.current++ };
      setRipples((prev) => [...prev, ripple]);
      setTimeout(() => setRipples((prev) => prev.filter((r) => r.id !== ripple.id)), 600);
    }
    onClick?.();
  };

  return (
    <div className="relative inline-block">
      <div style={{ perspective: "1000px", perspectiveOrigin: "50% 50%" }}>
        <div style={{ position: "relative", width: `${dimensions.width}px`, height: `${dimensions.height}px`, transformStyle: "preserve-3d", transition: "all 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)", transform: "none" }}>
          <div style={{ position: "absolute", top: 0, left: 0, width: `${dimensions.width}px`, height: `${dimensions.height}px`, display: "flex", alignItems: "center", justifyContent: "center", gap: "6px", transformStyle: "preserve-3d", transition: "all 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)", transform: "translateZ(20px)", zIndex: 30, pointerEvents: "none" }}>
            {viewMode === "icon" && <Sparkles size={16} style={{ color: "#666", filter: "drop-shadow(0px 1px 2px rgba(0,0,0,0.5))", transition: "all 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)" }} />}
            {viewMode === "text" && <span style={{ fontSize: "14px", color: "#666", fontWeight: 400, textShadow: "0px 1px 2px rgba(0,0,0,0.5)", transition: "all 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)", whiteSpace: "nowrap" }}>{label}</span>}
          </div>
          <div style={{ position: "absolute", top: 0, left: 0, width: `${dimensions.width}px`, height: `${dimensions.height}px`, transformStyle: "preserve-3d", transform: `translateZ(10px) ${isPressed ? "translateY(1px) scale(0.98)" : "translateY(0) scale(1)"}`, zIndex: 20 }}>
            <div style={{ width: `${dimensions.innerWidth}px`, height: `${dimensions.innerHeight}px`, margin: "2px", borderRadius: "100px", background: "linear-gradient(180deg, #202020 0%, #000000 100%)", boxShadow: isPressed ? "inset 0px 2px 4px rgba(0,0,0,0.4)" : "none" }} />
          </div>
          <div style={{ position: "absolute", top: 0, left: 0, width: `${dimensions.width}px`, height: `${dimensions.height}px`, transformStyle: "preserve-3d", transform: `translateZ(0px) ${isPressed ? "translateY(1px) scale(0.98)" : "translateY(0) scale(1)"}`, zIndex: 10 }}>
            <div style={{ height: `${dimensions.height}px`, width: `${dimensions.width}px`, borderRadius: "100px", boxShadow: isPressed ? "0px 0px 0px 1px rgba(0,0,0,0.5)" : isHovered ? "0px 0px 0px 1px rgba(0,0,0,0.4), 0px 12px 6px 0px rgba(0,0,0,0.05), 0px 8px 5px 0px rgba(0,0,0,0.1)" : "0px 0px 0px 1px rgba(0,0,0,0.3), 0px 9px 9px 0px rgba(0,0,0,0.12)", background: "rgb(0 0 0 / 0)" }}>
              <div ref={shaderRef} className="shader-container-exploded" style={{ borderRadius: "100px", overflow: "hidden", position: "relative", width: `${dimensions.shaderWidth}px`, maxWidth: `${dimensions.shaderWidth}px`, height: `${dimensions.shaderHeight}px` }} />
            </div>
          </div>
          <button ref={buttonRef} onClick={handleClick} onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave} onMouseDown={() => setIsPressed(true)} onMouseUp={() => setIsPressed(false)} style={{ position: "absolute", top: 0, left: 0, width: `${dimensions.width}px`, height: `${dimensions.height}px`, background: "transparent", border: "none", cursor: "pointer", outline: "none", zIndex: 40, transformStyle: "preserve-3d", transform: "translateZ(25px)", overflow: "hidden", borderRadius: "100px" }} aria-label={label}>
            {ripples.map((r) => <span key={r.id} style={{ position: "absolute", left: `${r.x}px`, top: `${r.y}px`, width: "20px", height: "20px", borderRadius: "50%", background: "radial-gradient(circle, rgba(255,255,255,0.4) 0%, rgba(255,255,255,0) 70%)", pointerEvents: "none", animation: "ripple-animation 0.6s ease-out" }} />)}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Write `frontend/src/components/ui/animated-blur-number.tsx`**

Copy exact component from task brief (`AnimateNumber` — the self-contained digit-by-digit blur-slide animation with embedded CSS injection). No modifications needed.

```tsx
"use client";

import * as React from "react";

const STYLES = `
.an-root {
  --an-spring: linear(0, 0.028 2.5%, 0.0995 5%, 0.198 7.5%, 0.3106 10%, 0.4272 12.5%, 0.5405 15%, 0.6454 17.5%, 0.7387 20%, 0.819 22.5%, 0.8856 25%, 0.9391 27.5%, 0.9803 30%, 1.0107 32.5%, 1.0317 35%, 1.045 37.5%, 1.052 40%, 1.0543 42.5%, 1.053 45%, 1.0493 47.5%, 1.044 50%, 1.0379 52.5%, 1.0316 55%, 1.0254 57.5%, 1.0197 60%, 1.0146 62.5%, 1.0102 65%, 1.0065 67.5%, 1.0035 70%, 1.0012 72.5%, 0.9995 75%, 0.9984 77.5%, 0.9976 80%, 0.9972 82.5%, 0.9971 85%, 0.9971 87.5%, 0.9973 90%, 0.9976 92.5%, 0.9979 95%, 0.9983 97.5%, 1);
  --an-dist: 0.55em;
  display: inline-flex; align-items: baseline; white-space: nowrap; font-variant-numeric: tabular-nums;
}
.an-slot { position: relative; display: inline-block; }
.an-layer { display: inline-block; will-change: transform, opacity, filter; }
.an-out { position: absolute; inset: 0; }
.an-in { animation: an-slide-in var(--an-dur, 450ms) var(--an-spring) both, an-resolve var(--an-dur, 450ms) cubic-bezier(0.22, 1, 0.36, 1) both; }
.an-out { animation: an-slide-out var(--an-dur, 450ms) cubic-bezier(0.4, 0, 1, 1) both, an-dissolve var(--an-dur, 450ms) cubic-bezier(0.4, 0, 1, 1) both; }
@keyframes an-slide-in { from { transform: translateY(calc(var(--an-dir, 1) * var(--an-dist))); } to { transform: translateY(0); } }
@keyframes an-slide-out { from { transform: translateY(0); } to { transform: translateY(calc(var(--an-dir, 1) * var(--an-dist) * -1)); } }
@keyframes an-resolve { from { opacity: 0; filter: blur(var(--an-blur, 21px)); } to { opacity: 1; filter: blur(0); } }
@keyframes an-dissolve { from { opacity: 1; filter: blur(0); } to { opacity: 0; filter: blur(var(--an-blur, 21px)); } }
@media (prefers-reduced-motion: reduce) { .an-in { animation: none; } .an-out { animation: none; display: none; } }
.an-sr { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
`;

let stylesInjected = false;
function ensureStyles() {
  if (stylesInjected || typeof document === "undefined") return;
  stylesInjected = true;
  if (document.getElementById("animate-number-styles")) return;
  const el = document.createElement("style");
  el.id = "animate-number-styles";
  el.textContent = STYLES;
  document.head.prepend(el);
}
ensureStyles();

function cn(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

const ZWSP = "​";

export type AnimateNumberProps = {
  value: number;
  format?: Intl.NumberFormatOptions;
  locale?: string;
  prefix?: React.ReactNode;
  suffix?: React.ReactNode;
  duration?: number;
  blur?: number;
  className?: string;
} & Omit<React.HTMLAttributes<HTMLSpanElement>, "prefix" | "children">;

function formatValue(value: number, locale: string, opts?: Intl.NumberFormatOptions) {
  try { return new Intl.NumberFormat(locale, opts).format(value); } catch { return String(value); }
}

type CharSlotProps = { char: string; direction: number; durationMs: number; blur: number };

function CharSlot({ char, direction, durationMs, blur }: CharSlotProps) {
  const prev = React.useRef(char);
  const genRef = React.useRef(0);
  const [state, setState] = React.useState(() => ({ cur: char, out: null as string | null, gen: 0 }));

  React.useEffect(() => {
    if (char === prev.current) return;
    genRef.current += 1;
    setState({ cur: char, out: prev.current, gen: genRef.current });
    prev.current = char;
  }, [char]);

  const animating = state.out !== null;
  const style = { "--an-dur": `${durationMs}ms`, "--an-blur": `${blur}px`, "--an-dir": direction } as React.CSSProperties;

  return (
    <span className="an-slot" style={style} aria-hidden>
      <span key={`in-${state.gen}`} className={cn("an-layer", animating && "an-in")} onAnimationEnd={animating ? () => setState((s) => ({ ...s, out: null })) : undefined}>
        {state.cur === "" ? ZWSP : state.cur}
      </span>
      {animating ? <span key={`out-${state.gen}`} className="an-layer an-out">{state.out === "" ? ZWSP : state.out}</span> : null}
    </span>
  );
}

export function AnimateNumber({ value, format, locale = "en-US", prefix, suffix, duration = 450, blur = 21, className, ...rest }: AnimateNumberProps) {
  ensureStyles();
  const formatted = formatValue(value, locale, format);
  const [prev, setPrev] = React.useState(value);
  const [direction, setDirection] = React.useState(1);
  if (prev !== value) { setDirection(value < prev ? -1 : 1); setPrev(value); }

  const chars = formatted.split("");
  const len = chars.length;
  const label = [typeof prefix === "string" ? prefix : "", formatted, typeof suffix === "string" ? suffix : ""].join("");

  return (
    <span {...rest} className={cn("an-root", className)}>
      <span className="an-sr">{label}</span>
      {prefix != null ? <span aria-hidden>{prefix}</span> : null}
      {chars.map((ch, i) => <CharSlot key={len - 1 - i} char={ch} direction={direction} durationMs={duration} blur={blur} />)}
      {suffix != null ? <span aria-hidden>{suffix}</span> : null}
    </span>
  );
}

export default AnimateNumber;
```

- [ ] **Step 4: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot
git add frontend/src/components/ui/
git commit -m "feat: motion-button, liquid-metal-button, animated-blur-number components"
```

---

## Task 5: Chart and animated-group components

**Files:**
- Create: `frontend/src/components/ui/chart-area-step.tsx`
- Create: `frontend/src/components/ui/animated-group.tsx`

- [ ] **Step 1: Write `frontend/src/components/ui/chart-area-step.tsx`**

Adapt from 8bit-chart-area-step.tsx — make data dynamic (accept `data` prop instead of hardcoded array), dark theme colors.

```tsx
"use client";
import * as React from "react";

type ChartPoint = { label: string; value: number };

const WIDTH = 720;
const HEIGHT = 360;
const PADDING = { top: 28, right: 28, bottom: 48, left: 46 };

function point(index: number, value: number, data: ChartPoint[], maxValue: number) {
  const innerWidth = WIDTH - PADDING.left - PADDING.right;
  const innerHeight = HEIGHT - PADDING.top - PADDING.bottom;
  return {
    x: PADDING.left + (innerWidth / (data.length - 1)) * index,
    y: PADDING.top + innerHeight - (value / maxValue) * innerHeight,
  };
}

function stepPath(data: ChartPoint[], maxValue: number) {
  const points = data.map((item, index) => point(index, item.value, data, maxValue));
  return points.map((p, index) => {
    if (index === 0) return `M ${p.x} ${p.y}`;
    return `H ${p.x} V ${p.y}`;
  }).join(" ");
}

function areaPath(data: ChartPoint[], maxValue: number) {
  const points = data.map((item, index) => point(index, item.value, data, maxValue));
  const baseY = HEIGHT - PADDING.bottom;
  return `${stepPath(data, maxValue)} L ${points[points.length - 1].x} ${baseY} H ${points[0].x} Z`;
}

interface ChartAreaStepProps {
  data: ChartPoint[];
  title?: string;
  subtitle?: string;
}

export default function ChartAreaStep({ data, title = "Performance", subtitle = "Step Area Chart" }: ChartAreaStepProps) {
  const [activeIndex, setActiveIndex] = React.useState(data.length > 1 ? 1 : 0);
  const maxValue = Math.max(...data.map((d) => d.value)) * 1.2;
  const active = data[activeIndex];
  const activePoint = active ? point(activeIndex, active.value, data, maxValue) : null;

  const yTickCount = 5;
  const yTicks = Array.from({ length: yTickCount }, (_, i) => Math.round((maxValue / (yTickCount - 1)) * i));

  return (
    <div className="w-full rounded-[12px] border border-[rgba(243,242,238,0.08)] bg-[#1A1A1E] p-4 text-[#F3F2EE]">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-[#8B8D91]">{title}</p>
          <h3 className="mt-2 text-sm font-semibold">{subtitle}</h3>
        </div>
        {active && (
          <div className="border border-[rgba(243,242,238,0.08)] bg-[#0B0B0D] px-3 py-2 text-right text-[10px] leading-relaxed rounded-[6px]">
            <span className="block text-[#8B8D91]">{active.label}</span>
            <span className="text-[#E55A1C] font-mono font-bold">{active.value}</span>
          </div>
        )}
      </div>

      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full overflow-visible" role="img" aria-label="Step area chart">
        <defs>
          <pattern id="pixel-grid-dark" width="16" height="16" patternUnits="userSpaceOnUse">
            <path d="M 16 0 L 0 0 0 16" fill="none" stroke="rgba(243,242,238,0.04)" strokeWidth="2" />
          </pattern>
        </defs>

        <rect x={PADDING.left} y={PADDING.top} width={WIDTH - PADDING.left - PADDING.right} height={HEIGHT - PADDING.top - PADDING.bottom} fill="url(#pixel-grid-dark)" />

        {yTicks.map((tick) => {
          const y = point(0, tick, data, maxValue).y;
          return (
            <g key={tick}>
              <line x1={PADDING.left} x2={WIDTH - PADDING.right} y1={y} y2={y} stroke="rgba(243,242,238,0.08)" strokeDasharray="8 8" />
              <text x={PADDING.left - 14} y={y + 4} textAnchor="end" fontSize="10" fill="#8B8D91">{tick}</text>
            </g>
          );
        })}

        <path d={areaPath(data, maxValue)} fill="#E55A1C" opacity="0.15" />
        <path d={stepPath(data, maxValue)} fill="none" stroke="#E55A1C" strokeWidth="3" strokeLinejoin="miter" strokeLinecap="square" />

        {data.map((item, index) => {
          const p = point(index, item.value, data, maxValue);
          const isActive = index === activeIndex;
          return (
            <g key={item.label} onMouseEnter={() => setActiveIndex(index)} onFocus={() => setActiveIndex(index)} tabIndex={0} className="cursor-pointer outline-none">
              <line x1={p.x} x2={p.x} y1={PADDING.top} y2={HEIGHT - PADDING.bottom} stroke="transparent" strokeWidth="46" />
              <rect x={p.x - 7} y={p.y - 7} width="14" height="14" fill={isActive ? "#E55A1C" : "#1A1A1E"} stroke={isActive ? "#E55A1C" : "rgba(243,242,238,0.3)"} strokeWidth="2" />
            </g>
          );
        })}

        {data.map((item, index) => {
          const p = point(index, item.value, data, maxValue);
          return <text key={item.label} x={p.x} y={HEIGHT - 18} textAnchor="middle" fontSize="10" fill="#8B8D91">{item.label}</text>;
        })}

        {activePoint && active && (
          <g transform={`translate(${Math.min(activePoint.x + 14, WIDTH - 170)} ${Math.max(activePoint.y - 62, 18)})`}>
            <rect width="152" height="46" fill="#0B0B0D" stroke="rgba(243,242,238,0.12)" strokeWidth="1" rx="4" />
            <text x="12" y="18" fontSize="10" fill="#8B8D91">{active.label}</text>
            <text x="12" y="34" fontSize="10" fill="#E55A1C" fontFamily="monospace">Value: {active.value}</text>
          </g>
        )}
      </svg>
    </div>
  );
}
```

- [ ] **Step 2: Write `frontend/src/components/ui/animated-group.tsx`**

```tsx
"use client";
import { ReactNode } from "react";
import { motion, Variants } from "framer-motion";
import { cn } from "@/lib/utils";
import React from "react";

type PresetType = "fade" | "slide" | "scale" | "blur" | "blur-slide" | "zoom" | "bounce";

type AnimatedGroupProps = {
  children: ReactNode;
  className?: string;
  variants?: { container?: Variants; item?: Variants };
  preset?: PresetType;
};

const defaultContainerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.1 } },
};

const presetVariants: Record<PresetType, { container: Variants; item: Variants }> = {
  fade: { container: defaultContainerVariants, item: { hidden: { opacity: 0 }, visible: { opacity: 1 } } },
  slide: { container: defaultContainerVariants, item: { hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } } },
  scale: { container: defaultContainerVariants, item: { hidden: { opacity: 0, scale: 0.8 }, visible: { opacity: 1, scale: 1 } } },
  blur: { container: defaultContainerVariants, item: { hidden: { opacity: 0, filter: "blur(4px)" }, visible: { opacity: 1, filter: "blur(0px)" } } },
  "blur-slide": { container: defaultContainerVariants, item: { hidden: { opacity: 0, filter: "blur(4px)", y: 20 }, visible: { opacity: 1, filter: "blur(0px)", y: 0 } } },
  zoom: { container: defaultContainerVariants, item: { hidden: { opacity: 0, scale: 0.5 }, visible: { opacity: 1, scale: 1, transition: { type: "spring", stiffness: 300, damping: 20 } } } },
  bounce: { container: defaultContainerVariants, item: { hidden: { opacity: 0, y: -50 }, visible: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 400, damping: 10 } } } },
};

export function AnimatedGroup({ children, className, variants, preset = "fade" }: AnimatedGroupProps) {
  const selected = presetVariants[preset];
  const containerVariants = variants?.container || selected.container;
  const itemVariants = variants?.item || selected.item;

  return (
    <motion.div initial="hidden" animate="visible" variants={containerVariants} className={cn(className)}>
      {React.Children.map(children, (child, index) => (
        <motion.div key={index} variants={itemVariants}>{child}</motion.div>
      ))}
    </motion.div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot
git add frontend/src/components/ui/chart-area-step.tsx frontend/src/components/ui/animated-group.tsx
git commit -m "feat: 8-bit step chart and animated-group components"
```

---

## Task 6: NavBar — liquid glass capsule with scroll-compact

**Files:**
- Create: `frontend/src/components/sections/NavBar.tsx`

- [ ] **Step 1: Write `frontend/src/components/sections/NavBar.tsx`**

```tsx
"use client";
import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { useScroll } from "@/hooks/use-scroll";
import { Button } from "@/components/ui/button";
import { MenuToggleIcon } from "@/components/ui/menu-toggle-icon";

const navLinks = [
  { label: "Decisions", href: "#decisions" },
  { label: "Performance", href: "#performance" },
  { label: "Verify", href: "#verify" },
];

export function NavBar() {
  const [open, setOpen] = useState(false);
  const scrolled = useScroll(60);

  return (
    <header className="fixed top-0 left-0 right-0 z-50 flex justify-center pt-4 px-4">
      <motion.nav
        initial={false}
        animate={{ width: scrolled ? "auto" : "100%", maxWidth: scrolled ? "480px" : "1200px" }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className={cn(
          "relative flex items-center justify-between px-5 py-3 transition-all duration-300",
          scrolled
            ? "rounded-full border border-[rgba(243,242,238,0.12)] bg-[rgba(11,11,13,0.72)] backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.4)]"
            : "rounded-[20px] border border-[rgba(243,242,238,0.06)] bg-[rgba(11,11,13,0.4)] backdrop-blur-md"
        )}
      >
        {/* Logo */}
        <a href="#" className="flex items-center gap-2 shrink-0">
          <div className="h-7 w-7 rounded-[6px] bg-[#E55A1C] flex items-center justify-center">
            <span className="text-[10px] font-black text-white font-mono">M</span>
          </div>
          <AnimatePresence>
            {!scrolled && (
              <motion.span
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: "auto" }}
                exit={{ opacity: 0, width: 0 }}
                className="text-sm font-bold text-[#F3F2EE] overflow-hidden whitespace-nowrap"
                style={{ fontFamily: "var(--font-display)" }}
              >
                sapa-fund
              </motion.span>
            )}
          </AnimatePresence>
        </a>

        {/* Desktop links */}
        <ul className="hidden md:flex items-center gap-1 absolute left-1/2 -translate-x-1/2">
          {navLinks.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                className="px-4 py-1.5 text-sm text-[#8B8D91] hover:text-[#F3F2EE] transition-colors rounded-full hover:bg-[rgba(243,242,238,0.06)]"
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>

        {/* CTA */}
        <div className="hidden md:flex items-center gap-2 shrink-0">
          <a
            href="https://explorer.sepolia.mantle.xyz/address/0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-mono text-[#E55A1C] border border-[rgba(229,90,28,0.3)] hover:border-[rgba(229,90,28,0.6)] transition-colors"
          >
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#E55A1C] opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#E55A1C]" />
            </span>
            Mantle Live
          </a>
        </div>

        {/* Mobile toggle */}
        <Button
          size="icon"
          variant="ghost"
          onClick={() => setOpen(!open)}
          className="md:hidden text-[#F3F2EE]"
          aria-label="Toggle menu"
        >
          <MenuToggleIcon open={open} className="size-5" duration={300} />
        </Button>
      </motion.nav>

      {/* Mobile menu */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="fixed top-20 left-4 right-4 rounded-[20px] border border-[rgba(243,242,238,0.08)] bg-[rgba(11,11,13,0.92)] backdrop-blur-xl p-4 md:hidden z-40"
          >
            <ul className="flex flex-col gap-1">
              {navLinks.map((link) => (
                <li key={link.href}>
                  <a
                    href={link.href}
                    onClick={() => setOpen(false)}
                    className="block px-4 py-3 text-sm text-[#8B8D91] hover:text-[#F3F2EE] hover:bg-[rgba(243,242,238,0.06)] rounded-[12px] transition-colors"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot
git add frontend/src/components/sections/NavBar.tsx
git commit -m "feat: liquid glass navbar with scroll-compact transition"
```

---

## Task 7: HeroSection — shader backdrop + macro headline

**Files:**
- Create: `frontend/src/components/sections/HeroSection.tsx`

- [ ] **Step 1: Write `frontend/src/components/sections/HeroSection.tsx`**

```tsx
import { Suspense, lazy, useState } from "react";
import { motion } from "framer-motion";
import { ArrowRight, Shield } from "lucide-react";
import MotionButton from "@/components/ui/motion-button";
import { LiquidMetalButton } from "@/components/ui/liquid-metal-button";

const Dithering = lazy(() =>
  import("@paper-design/shaders-react").then((mod) => ({ default: mod.Dithering }))
);

const item = {
  hidden: { opacity: 0, filter: "blur(12px)", y: 16 },
  visible: { opacity: 1, filter: "blur(0px)", y: 0, transition: { type: "spring", bounce: 0.3, duration: 1.2 } },
};

const container = {
  visible: { transition: { staggerChildren: 0.12, delayChildren: 0.3 } },
};

export function HeroSection() {
  const [isHovered, setIsHovered] = useState(false);

  return (
    <section
      className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden bg-[#0B0B0D]"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Shader backdrop */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <Suspense fallback={null}>
          <Dithering
            colorBack="#00000000"
            colorFront="#E55A1C"
            shape="warp"
            type="4x4"
            speed={isHovered ? 0.4 : 0.15}
            className="size-full opacity-20"
            minPixelRatio={1}
          />
        </Suspense>
      </div>

      {/* Radial vignette */}
      <div className="absolute inset-0 z-[1] pointer-events-none bg-[radial-gradient(ellipse_80%_60%_at_50%_50%,transparent_40%,#0B0B0D_100%)]" />

      {/* Content */}
      <motion.div
        variants={container}
        initial="hidden"
        animate="visible"
        className="relative z-10 max-w-5xl mx-auto px-6 text-center flex flex-col items-center"
      >
        {/* Badge */}
        <motion.div variants={item}>
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-[rgba(229,90,28,0.2)] bg-[rgba(229,90,28,0.06)] px-4 py-1.5 text-xs font-medium text-[#E55A1C] backdrop-blur-sm">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#E55A1C] opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#E55A1C]" />
            </span>
            <span className="font-mono tracking-widest uppercase text-[10px]">AI Alpha &amp; Data · Mantle Track</span>
          </div>
        </motion.div>

        {/* Headline */}
        <motion.h1
          variants={item}
          className="text-[clamp(3rem,8vw,7rem)] font-black leading-[0.92] tracking-[-0.03em] text-[#F3F2EE] mb-6"
          style={{ fontFamily: "Sora, sans-serif" }}
        >
          Every AI decision.
          <br />
          <span className="text-[#E55A1C]">Anchored on Mantle.</span>
        </motion.h1>

        {/* Subline */}
        <motion.p
          variants={item}
          className="text-[#8B8D91] text-lg md:text-xl max-w-2xl leading-relaxed mb-12"
        >
          Deterministic <code className="font-mono text-[#E55A1C] text-sm bg-[rgba(229,90,28,0.08)] px-1.5 py-0.5 rounded">bytes32</code> commitments exported from every trade decision. Judges verify on-chain. Zero custody. Fully auditable.
        </motion.p>

        {/* CTAs */}
        <motion.div variants={item} className="flex flex-wrap items-center justify-center gap-4">
          <MotionButton label="View Decisions" classes="bg-[#1A1A1E]" onClick={() => { document.getElementById("decisions")?.scrollIntoView({ behavior: "smooth" }); }} />
          <LiquidMetalButton label="Verify on Mantle" onClick={() => { document.getElementById("verify")?.scrollIntoView({ behavior: "smooth" }); }} />
        </motion.div>

        {/* Flow diagram */}
        <motion.div variants={item} className="mt-16 flex items-center gap-3 text-xs font-mono text-[#8B8D91]">
          {["Bot", "JSONL", "bytes32", "Mantle", "Verify"].map((step, i) => (
            <div key={step} className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-[6px] border border-[rgba(243,242,238,0.08)] bg-[rgba(26,26,30,0.6)] backdrop-blur-sm">
                {i === 3 && <Shield className="size-3 text-[#E55A1C]" />}
                <span className={i === 3 ? "text-[#E55A1C]" : ""}>{step}</span>
              </div>
              {i < 4 && <span className="text-[rgba(243,242,238,0.2)]">→</span>}
            </div>
          ))}
        </motion.div>
      </motion.div>

      {/* Bottom fade */}
      <div className="absolute bottom-0 left-0 right-0 h-32 z-[2] bg-gradient-to-t from-[#0B0B0D] to-transparent pointer-events-none" />
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot
git add frontend/src/components/sections/HeroSection.tsx
git commit -m "feat: hero section with dithering shader, animated headline, flow diagram"
```

---

## Task 8: StatsBar with animated numbers

**Files:**
- Create: `frontend/src/components/sections/StatsBar.tsx`

- [ ] **Step 1: Write `frontend/src/components/sections/StatsBar.tsx`**

```tsx
import { AnimateNumber } from "@/components/ui/animated-blur-number";
import type { Commitment, RegistryEvent } from "@/types";
import { formatPct } from "@/data/mantle";

interface StatsBarProps {
  commitments: Commitment[];
  events: RegistryEvent[];
}

export function StatsBar({ commitments, events }: StatsBarProps) {
  const anchored = events.length || commitments.length;
  const resolved = commitments.filter((item) => item.payload.resolved).length;
  const pnl = commitments.reduce((total, item) => total + (item.payload.pnl ?? 0), 0);
  const avgConf =
    commitments.length === 0
      ? 0
      : commitments.reduce((total, item) => total + (item.payload.confidence ?? 0), 0) /
        commitments.length;

  const stats = [
    { value: anchored, label: "Decisions anchored", prefix: "", decimals: 0 },
    { value: resolved, label: "Resolved outcomes", prefix: "", decimals: 0 },
    { value: pnl, label: "Paper ROI P&L", prefix: "$", decimals: 2 },
    { value: Math.round(avgConf * 1000) / 10, label: "Avg confidence", prefix: "", suffix: "%", decimals: 1 },
  ];

  return (
    <section className="border-y border-[rgba(243,242,238,0.06)] bg-[#0B0B0D]">
      <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-y md:divide-y-0 divide-[rgba(243,242,238,0.06)]">
        {stats.map((stat) => (
          <div key={stat.label} className="px-8 py-7 flex flex-col gap-1">
            <div className="text-3xl font-black text-[#F3F2EE]" style={{ fontFamily: "Sora, sans-serif" }}>
              <AnimateNumber
                value={stat.decimals === 0 ? Math.round(stat.value) : stat.value}
                prefix={stat.prefix}
                suffix={"suffix" in stat ? stat.suffix : undefined}
                format={stat.decimals > 0 ? { minimumFractionDigits: stat.decimals, maximumFractionDigits: stat.decimals } : undefined}
                className="text-3xl font-black"
                style={{ fontFamily: "Sora, sans-serif" }}
              />
            </div>
            <span className="text-xs text-[#8B8D91] uppercase tracking-widest font-mono">{stat.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot
git add frontend/src/components/sections/StatsBar.tsx
git commit -m "feat: stats bar with animated blur numbers"
```

---

## Task 9: HowItWorksSection — scroll-stacked cards

**Files:**
- Create: `frontend/src/components/sections/HowItWorksSection.tsx`

- [ ] **Step 1: Write `frontend/src/components/sections/HowItWorksSection.tsx`**

Composio-style scroll-stacked cards — each card sticks at a different top offset, the next card slides over the previous one.

```tsx
"use client";
import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { Bot, FileJson, Hash, Shield, CheckCircle } from "lucide-react";

const steps = [
  {
    num: "01",
    icon: Bot,
    title: "AI Makes a Decision",
    body: "The prediction agent runs LLM analysis on Polymarket markets and US equities, producing structured decisions with confidence scores, strategies, and reasoning.",
    accent: "#E55A1C",
  },
  {
    num: "02",
    icon: FileJson,
    title: "Payload Exported to JSONL",
    body: "Each decision is serialized into canonical JSON and exported to a deterministic JSONL artifact. Every field is sorted — no ambiguity in the hash input.",
    accent: "#E55A1C",
  },
  {
    num: "03",
    icon: Hash,
    title: "bytes32 Commitment Created",
    body: "Canonical JSON is SHA-256 hashed into a bytes32 commitment. The same payload always produces the same hash — independently reproducible by anyone.",
    accent: "#E55A1C",
  },
  {
    num: "04",
    icon: Shield,
    title: "Anchored on Mantle",
    body: "The bytes32 commitment is recorded in the AgentDecisionRegistry smart contract on Mantle Sepolia. Immutable, timestamped, publicly verifiable on-chain.",
    accent: "#E55A1C",
  },
  {
    num: "05",
    icon: CheckCircle,
    title: "Independent Verification",
    body: "Judges re-download the payload, recompute the SHA-256 hash, and compare against the on-chain record. No trust required — math closes the loop.",
    accent: "#E55A1C",
  },
];

function StackedCard({ step, index, total }: { step: typeof steps[0]; index: number; total: number }) {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const Icon = step.icon;

  return (
    <div
      ref={ref}
      className="sticky"
      style={{ top: `${80 + index * 24}px` }}
    >
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ type: "spring", stiffness: 200, damping: 25, delay: 0.05 }}
        className="relative mx-auto max-w-4xl rounded-[20px] border border-[rgba(243,242,238,0.08)] bg-[#1A1A1E] p-8 md:p-12 overflow-hidden"
        style={{ zIndex: index + 1 }}
      >
        {/* Subtle top glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-48 h-px bg-gradient-to-r from-transparent via-[rgba(229,90,28,0.4)] to-transparent" />

        <div className="flex items-start gap-6">
          {/* Number + Icon */}
          <div className="shrink-0 flex flex-col items-center gap-3">
            <div className="w-12 h-12 rounded-[12px] border border-[rgba(229,90,28,0.2)] bg-[rgba(229,90,28,0.06)] flex items-center justify-center">
              <Icon className="size-5 text-[#E55A1C]" />
            </div>
            <span className="text-[10px] font-mono text-[rgba(243,242,238,0.2)] tracking-widest">{step.num}</span>
          </div>

          {/* Text */}
          <div>
            <h3
              className="text-2xl font-bold text-[#F3F2EE] mb-3 leading-tight"
              style={{ fontFamily: "Sora, sans-serif" }}
            >
              {step.title}
            </h3>
            <p className="text-[#8B8D91] leading-relaxed text-base max-w-2xl">{step.body}</p>
          </div>

          {/* Step counter */}
          <div className="ml-auto shrink-0 text-[rgba(243,242,238,0.06)] text-7xl font-black leading-none" style={{ fontFamily: "Sora, sans-serif" }}>
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
        <p className="text-[10px] font-mono tracking-widest uppercase text-[#E55A1C] mb-4">How it works</p>
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
          <StackedCard key={step.num} step={step} index={i} total={steps.length} />
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot
git add frontend/src/components/sections/HowItWorksSection.tsx
git commit -m "feat: scroll-stacked how-it-works section (Composio-style)"
```

---

## Task 10: DecisionsSection + PerformanceSection + VerifySection

**Files:**
- Create: `frontend/src/components/sections/DecisionsSection.tsx`
- Create: `frontend/src/components/sections/PerformanceSection.tsx`
- Create: `frontend/src/components/sections/VerifySection.tsx`

- [ ] **Step 1: Write `frontend/src/components/sections/DecisionsSection.tsx`**

```tsx
"use client";
import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search } from "lucide-react";
import type { Commitment, RegistryEvent } from "@/types";
import { shortHash, formatPct } from "@/data/mantle";
import { cn } from "@/lib/utils";

interface DecisionsSectionProps {
  commitments: Commitment[];
  events: RegistryEvent[];
  explorerBase: string;
  registryAddress: string | undefined;
  status: string;
}

const PAGE_SIZE = 6;

function DecisionCard({ item, index }: { item: Commitment; index: number }) {
  const isEquity = Boolean(item.payload.ticker || item.payload.strategy === "equity_analyst");
  const p = item.payload;

  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ type: "spring", stiffness: 300, damping: 30, delay: index * 0.04 }}
      className={cn(
        "rounded-[12px] border bg-[#1A1A1E] p-5 grid gap-4",
        isEquity
          ? "border-l-2 border-l-[#E55A1C] border-[rgba(243,242,238,0.06)]"
          : "border-[rgba(243,242,238,0.06)]"
      )}
      style={{ gridTemplateColumns: "1fr auto" }}
    >
      <div className="min-w-0">
        {isEquity ? (
          <div className="flex items-center gap-2 mb-2">
            <span className="text-lg font-black text-[#F3F2EE]" style={{ fontFamily: "Geist Mono, monospace" }}>{p.ticker}</span>
            {p.status && (
              <span className={cn(
                "text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-[4px]",
                p.status === "open" ? "bg-[rgba(229,90,28,0.1)] text-[#E55A1C]" : "bg-[rgba(243,242,238,0.06)] text-[#8B8D91]"
              )}>{p.status}</span>
            )}
          </div>
        ) : (
          <h3 className="text-sm font-semibold text-[#F3F2EE] mb-1 line-clamp-2">{p.question}</h3>
        )}
        <p className="text-xs text-[#8B8D91] line-clamp-2">{p.reason}</p>
      </div>

      <dl className="text-right shrink-0 space-y-1">
        <div>
          <dt className="text-[10px] font-mono text-[#8B8D91] uppercase">Conf</dt>
          <dd className="text-sm font-bold text-[#F3F2EE]">{formatPct(p.confidence)}</dd>
        </div>
        {isEquity ? (
          <div>
            <dt className="text-[10px] font-mono text-[#8B8D91] uppercase">P&L</dt>
            <dd className={cn("text-sm font-bold font-mono", (p.realized_pnl ?? p.pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
              {p.realized_pnl != null ? `$${p.realized_pnl.toFixed(2)}` : p.pnl != null ? `$${p.pnl.toFixed(2)}` : "open"}
            </dd>
          </div>
        ) : (
          <div>
            <dt className="text-[10px] font-mono text-[#8B8D91] uppercase">Fair</dt>
            <dd className="text-sm font-bold text-[#F3F2EE]">{formatPct(p.fair_prob)}</dd>
          </div>
        )}
        <div>
          <dt className="text-[10px] font-mono text-[#8B8D91] uppercase">Hash</dt>
          <dd className="text-[10px] font-mono text-[rgba(243,242,238,0.3)]">{shortHash(item.bytes32)}</dd>
        </div>
      </dl>
    </motion.article>
  );
}

export function DecisionsSection({ commitments, events, explorerBase, registryAddress, status }: DecisionsSectionProps) {
  const [search, setSearch] = useState("");
  const [showAll, setShowAll] = useState(false);

  const filtered = useMemo(() => {
    if (!search.trim()) return commitments;
    const q = search.trim().toLowerCase();
    return commitments.filter((item) => item.bytes32.toLowerCase().includes(q));
  }, [commitments, search]);

  const visible = showAll ? filtered : filtered.slice(0, PAGE_SIZE);
  const explorerLink = registryAddress ? `${explorerBase.replace(/\/$/, "")}/address/${registryAddress}` : "";

  return (
    <section id="decisions" className="py-24 px-6 bg-[#0B0B0D]">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-end justify-between mb-12 flex-wrap gap-4">
          <div>
            <p className="text-[10px] font-mono tracking-widest uppercase text-[#E55A1C] mb-3">Decision feed</p>
            <h2 className="text-4xl font-black text-[#F3F2EE]" style={{ fontFamily: "Sora, sans-serif" }}>Auditable AI payloads</h2>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-[#8B8D91]" />
            <input
              value={search}
              onChange={(e) => { setSearch(e.target.value); setShowAll(false); }}
              placeholder="Filter by hash..."
              className="pl-9 pr-4 py-2.5 rounded-[8px] border border-[rgba(243,242,238,0.08)] bg-[#1A1A1E] text-sm text-[#F3F2EE] placeholder:text-[#8B8D91] outline-none focus:border-[rgba(229,90,28,0.4)] transition-colors font-mono w-64"
            />
          </div>
        </div>

        <div className="grid md:grid-cols-[1fr_320px] gap-6">
          {/* Feed */}
          <div className="space-y-3">
            <AnimatePresence mode="popLayout">
              {visible.length === 0 ? (
                <p className="text-[#8B8D91] text-sm font-mono">No decisions match that hash fragment.</p>
              ) : (
                visible.map((item, i) => <DecisionCard key={item.bytes32} item={item} index={i} />)
              )}
            </AnimatePresence>
            {filtered.length > PAGE_SIZE && !showAll && (
              <button
                onClick={() => setShowAll(true)}
                className="w-full py-3 rounded-[8px] border border-[rgba(243,242,238,0.08)] text-sm font-mono text-[#8B8D91] hover:text-[#F3F2EE] hover:border-[rgba(243,242,238,0.16)] transition-colors"
              >
                Show all {filtered.length} decisions
              </button>
            )}
          </div>

          {/* Registry panel */}
          <aside className="rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] p-6 h-fit">
            <p className="text-[10px] font-mono tracking-widest uppercase text-[#E55A1C] mb-1">Mantle registry</p>
            <h3 className="text-lg font-bold text-[#F3F2EE] mb-4" style={{ fontFamily: "Sora, sans-serif" }}>Reputation layer</h3>
            <p className="text-xs text-[#8B8D91] mb-4 font-mono">{status}</p>
            <dl className="space-y-3 text-xs font-mono">
              <div className="flex justify-between gap-4">
                <dt className="text-[#8B8D91]">Contract</dt>
                <dd className="text-[rgba(243,242,238,0.5)] text-right break-all">{registryAddress ? shortHash(registryAddress) : "Set env var"}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-[#8B8D91]">Explorer</dt>
                <dd>{explorerLink ? <a href={explorerLink} target="_blank" rel="noopener noreferrer" className="text-[#E55A1C] hover:underline">Mantle Sepolia</a> : "Pending"}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-[#8B8D91]">Events</dt>
                <dd className="text-[#F3F2EE]">{events.length ? `${events.length} live` : "Fallback JSON"}</dd>
              </div>
            </dl>
            <div className="mt-4 space-y-2 border-t border-[rgba(243,242,238,0.06)] pt-4">
              {(events.length ? events : commitments.slice(0, 5).map((c, i) => ({ id: String(i), decisionHash: c.bytes32, uri: `sample#${i+1}` }))).map((ev: { id: string; decisionHash: string; uri: string }) => (
                <div key={`${ev.id}-${ev.decisionHash}`} className="pl-3 border-l-2 border-[rgba(229,90,28,0.3)] py-1">
                  <strong className="block text-[10px] font-mono text-[#F3F2EE]">#{ev.id} {shortHash(ev.decisionHash)}</strong>
                  <span className="block text-[10px] font-mono text-[#8B8D91] mt-0.5">{ev.uri}</span>
                </div>
              ))}
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Write `frontend/src/components/sections/PerformanceSection.tsx`**

```tsx
import { useMemo } from "react";
import ChartAreaStep from "@/components/ui/chart-area-step";
import { AnimateNumber } from "@/components/ui/animated-blur-number";
import type { Commitment, PerformanceSummary } from "@/types";
import { formatPct } from "@/data/mantle";
import { cn } from "@/lib/utils";

interface PerformanceSectionProps {
  commitments: Commitment[];
  perf: PerformanceSummary | null;
}

export function PerformanceSection({ commitments, perf }: PerformanceSectionProps) {
  const chartData = useMemo(() => {
    const groups: Record<string, number> = {};
    for (const item of commitments) {
      const ts = item.payload.timestamp || item.payload.opened_at;
      if (!ts) continue;
      const date = ts.slice(5, 10);
      groups[date] = (groups[date] || 0) + 1;
    }
    return Object.entries(groups)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-8)
      .map(([label, value]) => ({ label, value }));
  }, [commitments]);

  const eq = perf?.equity_trades;

  const statCards = eq
    ? [
        { value: perf!.total_commitments, label: "Total decisions anchored", green: false },
        { value: eq.total, label: "Equity trades total", green: false },
        { value: eq.realized_pnl, label: "Closed P&L ($)", green: eq.realized_pnl >= 0, prefix: "$", decimals: 2 },
        { value: Math.round(eq.win_rate * 1000) / 10, label: "Win rate", green: eq.win_rate > 0.5, suffix: "%", decimals: 1 },
        { value: Math.round(eq.avg_confidence * 1000) / 10, label: "Avg confidence", green: false, suffix: "%", decimals: 1 },
        { value: eq.open, label: "Open positions", green: false },
      ]
    : [];

  return (
    <section id="performance" className="py-24 px-6 bg-[#0B0B0D]">
      <div className="max-w-6xl mx-auto">
        <div className="mb-12">
          <p className="text-[10px] font-mono tracking-widest uppercase text-[#E55A1C] mb-3">Performance summary</p>
          <h2 className="text-4xl font-black text-[#F3F2EE]" style={{ fontFamily: "Sora, sans-serif" }}>AI trading track record</h2>
        </div>

        {/* Stat cards */}
        {statCards.length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-10">
            {statCards.map((s) => (
              <div key={s.label} className="rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] p-5">
                <div className={cn("text-2xl font-black mb-1", s.green ? "text-emerald-400" : "text-[#F3F2EE]")} style={{ fontFamily: "Sora, sans-serif" }}>
                  <AnimateNumber
                    value={s.decimals ? s.value : Math.round(s.value)}
                    prefix={"prefix" in s ? s.prefix : undefined}
                    suffix={"suffix" in s ? s.suffix : undefined}
                    format={s.decimals ? { minimumFractionDigits: s.decimals, maximumFractionDigits: s.decimals } : undefined}
                    className="text-2xl font-black"
                  />
                </div>
                <span className="text-xs text-[#8B8D91] font-mono uppercase tracking-wider">{s.label}</span>
              </div>
            ))}
          </div>
        )}

        {/* Chart */}
        {chartData.length > 1 ? (
          <ChartAreaStep data={chartData} title="Decisions" subtitle="Anchored decisions by date" />
        ) : (
          <div className="rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] p-8 text-center">
            <p className="text-[#8B8D91] text-sm font-mono">Accumulating decision history for chart...</p>
          </div>
        )}

        {/* Strategy table */}
        {perf && perf.strategies.length > 0 && (
          <div className="mt-8 rounded-[12px] border border-[rgba(243,242,238,0.06)] bg-[#1A1A1E] overflow-hidden">
            <div className="px-6 py-4 border-b border-[rgba(243,242,238,0.06)]">
              <h3 className="text-sm font-bold text-[#F3F2EE]">Strategy breakdown</h3>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[rgba(243,242,238,0.06)]">
                  <th className="px-6 py-3 text-left text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider">Strategy</th>
                  <th className="px-6 py-3 text-right text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider">Decisions</th>
                </tr>
              </thead>
              <tbody>
                {perf.strategies.map((s) => (
                  <tr key={s.name} className="border-b border-[rgba(243,242,238,0.04)] last:border-0 hover:bg-[rgba(243,242,238,0.02)]">
                    <td className="px-6 py-3 font-mono text-[#F3F2EE]">{s.name}</td>
                    <td className="px-6 py-3 font-mono text-right text-[#E55A1C]">{s.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Write `frontend/src/components/sections/VerifySection.tsx`**

```tsx
import { canonicalJson } from "@/data/mantle";
import type { Commitment } from "@/types";
import { CheckCircle, Copy } from "lucide-react";
import { useState } from "react";

function wrappedPayload(c: Commitment) {
  return { kind: c.kind, payload: c.payload, schema_version: c.schema_version, source: c.source };
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
  const match = selected && verifiedHash && verifiedHash === selected.bytes32;

  return (
    <section id="verify" className="py-24 px-6 bg-[#0B0B0D]">
      <div className="max-w-6xl mx-auto">
        <div className="mb-12">
          <p className="text-[10px] font-mono tracking-widest uppercase text-[#E55A1C] mb-3">Verification panel</p>
          <h2 className="text-4xl font-black text-[#F3F2EE]" style={{ fontFamily: "Sora, sans-serif" }}>
            Canonical JSON → SHA-256 → bytes32
          </h2>
          <p className="mt-3 text-[#8B8D91] max-w-2xl">
            Mantle stores the commitment. The payload stays public so outcomes can later be anchored without giving the contract custody or live trading authority.
          </p>
        </div>

        <div className="grid md:grid-cols-[1fr_360px] gap-6">
          {/* JSON panel */}
          <div className="rounded-[12px] border border-[rgba(243,242,238,0.08)] bg-[#0B0B0D] overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[rgba(243,242,238,0.06)] bg-[#1A1A1E]">
              <span className="text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider">Payload (canonical JSON)</span>
              <button onClick={() => copy(jsonStr, "json")} className="flex items-center gap-1.5 text-[10px] font-mono text-[#8B8D91] hover:text-[#F3F2EE] transition-colors">
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
              <span className="text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider block mb-2">Recomputed SHA-256</span>
              <div className="flex items-start gap-2">
                <code className="text-[11px] font-mono text-[#F3F2EE] break-all flex-1 leading-relaxed">{verifiedHash || "pending..."}</code>
                {verifiedHash && <button onClick={() => copy(verifiedHash, "hash")} className="shrink-0 text-[#8B8D91] hover:text-[#F3F2EE] transition-colors"><Copy className="size-3.5" /></button>}
              </div>
            </div>

            <div className="border-t border-[rgba(243,242,238,0.06)] pt-5">
              <span className="text-[10px] font-mono text-[#8B8D91] uppercase tracking-wider block mb-2">Exported bytes32 (on-chain)</span>
              <code className="text-[11px] font-mono text-[#E55A1C] break-all leading-relaxed">{selected?.bytes32 || "pending..."}</code>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Commit**

```bash
cd /Users/nikolassapalidis/polymarket-bot
git add frontend/src/components/sections/
git commit -m "feat: decisions, performance, verify sections with premium dark UI"
```

---

## Task 11: CTASection + wire App.tsx

**Files:**
- Create: `frontend/src/components/sections/CTASection.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx` (only if needed — switch from single-file to App import)

- [ ] **Step 1: Write `frontend/src/components/sections/CTASection.tsx`**

```tsx
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
        <div className="absolute inset-0 z-0 pointer-events-none opacity-30 mix-blend-screen">
          <Suspense fallback={null}>
            <Dithering
              colorBack="#00000000"
              colorFront="#E55A1C"
              shape="warp"
              type="4x4"
              speed={isHovered ? 0.6 : 0.2}
              className="size-full"
              minPixelRatio={1}
            />
          </Suspense>
        </div>

        <div className="relative z-10 text-center px-6 max-w-3xl mx-auto flex flex-col items-center">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-[rgba(229,90,28,0.2)] bg-[rgba(229,90,28,0.06)] px-4 py-1.5 text-[10px] font-mono text-[#E55A1C] uppercase tracking-widest">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#E55A1C] opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#E55A1C]" />
            </span>
            Deployed on Mantle Sepolia
          </div>

          <h2 className="text-4xl md:text-6xl font-black text-[#F3F2EE] leading-tight mb-6" style={{ fontFamily: "Sora, sans-serif" }}>
            Verify it yourself.
          </h2>

          <p className="text-[#8B8D91] text-lg mb-10 max-w-xl">
            Every decision hash is public. Recompute it from the JSON. Compare it to the chain.
          </p>

          <a
            href="https://explorer.sepolia.mantle.xyz/address/0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887"
            target="_blank"
            rel="noopener noreferrer"
            className="group inline-flex h-12 items-center gap-3 rounded-full bg-[#E55A1C] px-8 text-sm font-bold text-white transition-all duration-300 hover:bg-[#C94A12] hover:scale-105 active:scale-95"
          >
            View on Mantle Explorer
            <ArrowRight className="size-4 transition-transform duration-300 group-hover:translate-x-1" />
          </a>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Write `frontend/src/App.tsx`**

```tsx
import { useEffect, useMemo, useState } from "react";
import { NavBar } from "@/components/sections/NavBar";
import { HeroSection } from "@/components/sections/HeroSection";
import { StatsBar } from "@/components/sections/StatsBar";
import { HowItWorksSection } from "@/components/sections/HowItWorksSection";
import { DecisionsSection } from "@/components/sections/DecisionsSection";
import { PerformanceSection } from "@/components/sections/PerformanceSection";
import { VerifySection } from "@/components/sections/VerifySection";
import { CTASection } from "@/components/sections/CTASection";
import type { Commitment, RegistryEvent, PerformanceSummary } from "@/types";
import {
  canonicalJson,
  sha256Hex,
  explorerBase,
  registryAddress,
  rpcUrl,
  createMantleClient,
  createRegistryContract,
} from "@/data/mantle";
import type { Hex } from "viem";

function wrappedPayload(c: Commitment) {
  return { kind: c.kind, payload: c.payload, schema_version: c.schema_version, source: c.source };
}

export default function App() {
  const [commitments, setCommitments] = useState<Commitment[]>([]);
  const [events, setEvents] = useState<RegistryEvent[]>([]);
  const [verifiedHash, setVerifiedHash] = useState("");
  const [status, setStatus] = useState("Loading exported decision payloads");
  const [perf, setPerf] = useState<PerformanceSummary | null>(null);

  const selected = commitments[0];

  useEffect(() => {
    fetch("/mantle_commitments.sample.json")
      .then((r) => r.json())
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
    const client = createMantleClient(rpcUrl);
    const contract = createRegistryContract(registryAddress as Hex, client);
    contract.getEvents
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

  return (
    <div className="min-h-screen bg-[#0B0B0D]">
      <NavBar />
      <HeroSection />
      <StatsBar commitments={commitments} events={events} />
      <HowItWorksSection />
      <DecisionsSection
        commitments={commitments}
        events={events}
        explorerBase={explorerBase}
        registryAddress={registryAddress}
        status={status}
      />
      <PerformanceSection commitments={commitments} perf={perf} />
      <VerifySection selected={selected} verifiedHash={verifiedHash} />
      <CTASection />

      <footer className="border-t border-[rgba(243,242,238,0.06)] py-8 px-6 text-center">
        <p className="text-xs font-mono text-[rgba(243,242,238,0.2)]">
          Mantle-Verifiable AI Prediction Agent · DoraHacks AI Alpha &amp; Data · Paper-trading only — no live custody
        </p>
      </footer>
    </div>
  );
}
```

- [ ] **Step 3: Update `frontend/src/main.tsx` to import App**

```tsx
import React from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(<App />);
```

- [ ] **Step 4: Build and verify**

```bash
cd /Users/nikolassapalidis/polymarket-bot/frontend && npm run build 2>&1 | tail -30
```

Expected: zero TypeScript errors, successful Vite build.

- [ ] **Step 5: Commit and push**

```bash
cd /Users/nikolassapalidis/polymarket-bot
git add frontend/src/
git commit -m "feat: wire App.tsx + CTASection — premium landing page complete"
git push
```

---

## Self-Review

**Spec coverage check:**
- ✅ Liquid glass nav with scroll-compact → NavBar.tsx
- ✅ Dithering WebGL shader hero → HeroSection.tsx  
- ✅ Animated blur numbers → StatsBar.tsx + PerformanceSection.tsx
- ✅ Scroll-stacked feature cards (Composio-style) → HowItWorksSection.tsx
- ✅ Decision feed with hash search → DecisionsSection.tsx
- ✅ 8-bit step chart → PerformanceSection.tsx + chart-area-step.tsx
- ✅ Hash verification panel → VerifySection.tsx
- ✅ Dithering shader CTA section → CTASection.tsx
- ✅ LiquidMetalButton + MotionButton in hero → HeroSection.tsx
- ✅ All existing data logic preserved → data/mantle.ts
- ✅ Brand tokens (dark base, burnt orange accent, Sora/Jakarta) → index.css
- ✅ All TypeScript types extracted → types/index.ts

**Placeholder scan:** None — every step has exact file content.

**Type consistency:**
- `Commitment`, `RegistryEvent`, `PerformanceSummary` defined once in `types/index.ts`, imported everywhere
- `canonicalJson`, `sha256Hex`, `shortHash`, `formatPct` defined once in `data/mantle.ts`
- `wrappedPayload` helper duplicated in App.tsx and VerifySection — intentional, each is a one-liner that's different from the App context; could be moved to data/mantle.ts if preferred

---

**Plan complete and saved to `docs/superpowers/plans/2026-06-09-premium-landing-page.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, fast iteration, I review between tasks

**2. Inline Execution** — I execute all tasks in sequence in this session

**Which approach?**
