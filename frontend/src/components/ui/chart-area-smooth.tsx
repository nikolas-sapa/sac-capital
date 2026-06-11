import * as React from "react";

type ChartPoint = { label: string; value: number };

const WIDTH = 720;
const HEIGHT = 320;
const PAD = { top: 24, right: 24, bottom: 44, left: 56 };

interface Scale {
  min: number;
  max: number;
  range: number;
}

function makeScale(data: ChartPoint[]): Scale {
  const vals = data.map((d) => d.value);
  const rawMin = Math.min(...vals);
  const rawMax = Math.max(...vals);
  const min = Math.min(rawMin, 0);
  const max = Math.max(rawMax, 0);
  const range = Math.max(max - min, 0.01);
  const pad = range * 0.18;
  return { min: min - pad, max: max + pad, range: range + 2 * pad };
}

function pt(index: number, value: number, n: number, scale: Scale) {
  const iw = WIDTH - PAD.left - PAD.right;
  const ih = HEIGHT - PAD.top - PAD.bottom;
  return {
    x: PAD.left + (iw / Math.max(n - 1, 1)) * index,
    y: PAD.top + ih * (1 - (value - scale.min) / scale.range),
  };
}

function zeroY(scale: Scale) {
  const ih = HEIGHT - PAD.top - PAD.bottom;
  return PAD.top + ih * (1 - (0 - scale.min) / scale.range);
}

function smoothLinePath(data: ChartPoint[], scale: Scale): string {
  if (data.length === 0) return "";
  const points = data.map((item, i) => pt(i, item.value, data.length, scale));
  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    const p0 = points[i - 1];
    const p1 = points[i];
    const cpx = (p0.x + p1.x) / 2;
    d += ` C ${cpx} ${p0.y} ${cpx} ${p1.y} ${p1.x} ${p1.y}`;
  }
  return d;
}

function smoothAreaPath(data: ChartPoint[], scale: Scale): string {
  if (data.length === 0) return "";
  const points = data.map((item, i) => pt(i, item.value, data.length, scale));
  const baseY = zeroY(scale);
  const line = smoothLinePath(data, scale);
  return `${line} L ${points[points.length - 1].x} ${baseY} L ${points[0].x} ${baseY} Z`;
}

function fmtTick(v: number) {
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(1)}k`;
  if (Math.abs(v) < 0.01 && v !== 0) return `$${v.toFixed(4)}`;
  return `$${v.toFixed(2)}`;
}

interface ChartAreaSmoothProps {
  data: ChartPoint[];
  positive?: boolean;
}

export default function ChartAreaSmooth({ data, positive = true }: ChartAreaSmoothProps) {
  const [activeIndex, setActiveIndex] = React.useState<number>(data.length - 1);

  React.useEffect(() => {
    setActiveIndex(data.length - 1);
  }, [data.length]);

  if (data.length === 0) return null;

  const scale = makeScale(data);
  const active = data[Math.min(activeIndex, data.length - 1)];
  const activePoint = active ? pt(activeIndex, active.value, data.length, scale) : null;
  const z = zeroY(scale);
  const hasNegative = scale.min < 0;

  const lineColor = positive ? "#0b7bff" : "#f87171";
  const yTicks = Array.from({ length: 5 }, (_, i) => scale.min + (scale.range / 4) * i);

  // Thin out x labels if too many points
  const labelStep = data.length <= 10 ? 1 : data.length <= 30 ? Math.ceil(data.length / 8) : Math.ceil(data.length / 6);

  return (
    <div className="w-full">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-auto w-full overflow-visible"
        onMouseLeave={() => setActiveIndex(data.length - 1)}
      >
        <defs>
          <linearGradient id="smooth-area-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.18" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="0.01" />
          </linearGradient>
          <clipPath id="chart-clip">
            <rect x={PAD.left} y={PAD.top}
              width={WIDTH - PAD.left - PAD.right}
              height={HEIGHT - PAD.top - PAD.bottom} />
          </clipPath>
        </defs>

        {/* Grid lines */}
        {yTicks.map((tick, i) => {
          const y = pt(0, tick, data.length, scale).y;
          return (
            <g key={i}>
              <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y} y2={y}
                stroke="rgba(243,242,238,0.05)" strokeWidth="1" />
              <text x={PAD.left - 8} y={y + 4} textAnchor="end" fontSize="9" fill="#8B8D91" fontFamily="monospace">
                {fmtTick(tick)}
              </text>
            </g>
          );
        })}

        {/* Zero baseline */}
        {hasNegative && (
          <line x1={PAD.left} x2={WIDTH - PAD.right} y1={z} y2={z}
            stroke="rgba(243,242,238,0.2)" strokeWidth="1" strokeDasharray="4 3" />
        )}

        {/* Area fill */}
        <path d={smoothAreaPath(data, scale)} fill="url(#smooth-area-grad)" clipPath="url(#chart-clip)" />

        {/* Line */}
        <path d={smoothLinePath(data, scale)} fill="none"
          stroke={lineColor} strokeWidth="2" strokeLinecap="round"
          clipPath="url(#chart-clip)" />

        {/* Invisible wide hit targets */}
        {data.map((item, index) => {
          const p = pt(index, item.value, data.length, scale);
          const slotW = (WIDTH - PAD.left - PAD.right) / Math.max(data.length - 1, 1);
          return (
            <rect key={index}
              x={p.x - slotW / 2} y={PAD.top}
              width={slotW} height={HEIGHT - PAD.top - PAD.bottom}
              fill="transparent"
              onMouseEnter={() => setActiveIndex(index)}
            />
          );
        })}

        {/* Active dot */}
        {activePoint && (
          <>
            <line x1={activePoint.x} x2={activePoint.x}
              y1={PAD.top} y2={HEIGHT - PAD.bottom}
              stroke="rgba(243,242,238,0.1)" strokeWidth="1" strokeDasharray="4 3" />
            <circle cx={activePoint.x} cy={activePoint.y} r="4"
              fill="#0B0B0D" stroke={lineColor} strokeWidth="2" />
            <circle cx={activePoint.x} cy={activePoint.y} r="2"
              fill={lineColor} />
          </>
        )}

        {/* X labels */}
        {data.map((item, index) => {
          if (index % labelStep !== 0 && index !== data.length - 1) return null;
          const p = pt(index, item.value, data.length, scale);
          return (
            <text key={index} x={p.x} y={HEIGHT - 10}
              textAnchor="middle" fontSize="9" fill="#8B8D91" fontFamily="monospace">
              {item.label}
            </text>
          );
        })}

        {/* Tooltip */}
        {activePoint && active && (
          <g transform={`translate(${Math.min(Math.max(activePoint.x - 60, PAD.left), WIDTH - PAD.right - 120)},${PAD.top})`}>
            <rect width="120" height="38" rx="6"
              fill="rgba(26,26,30,0.95)" stroke="rgba(243,242,238,0.12)" strokeWidth="1" />
            <text x="10" y="14" fontSize="9" fill="#8B8D91" fontFamily="monospace">{active.label}</text>
            <text x="10" y="28" fontSize="11" fontFamily="monospace" fontWeight="700"
              fill={active.value >= 0 ? "#0b7bff" : "#f87171"}>
              {active.value >= 0 ? "+" : ""}{fmtTick(active.value)}
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
