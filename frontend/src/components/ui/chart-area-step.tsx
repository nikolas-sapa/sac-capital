import * as React from "react";

type ChartPoint = { label: string; value: number };

const WIDTH = 720;
const HEIGHT = 360;
const PAD = { top: 28, right: 28, bottom: 48, left: 58 };

interface Scale {
  min: number;
  max: number;
  range: number;
}

function makeScale(data: ChartPoint[]): Scale {
  const vals = data.map((d) => d.value);
  const raw_min = Math.min(...vals);
  const raw_max = Math.max(...vals);
  // Always include 0 in the axis range
  const min = Math.min(raw_min, 0);
  const max = Math.max(raw_max, 0);
  const range = Math.max(max - min, 0.01);
  const pad = range * 0.15;
  return { min: min - pad, max: max + pad, range: range + 2 * pad };
}

function pt(index: number, value: number, data: ChartPoint[], scale: Scale) {
  const iw = WIDTH - PAD.left - PAD.right;
  const ih = HEIGHT - PAD.top - PAD.bottom;
  return {
    x: PAD.left + (iw / Math.max(data.length - 1, 1)) * index,
    y: PAD.top + ih * (1 - (value - scale.min) / scale.range),
  };
}

function zeroY(scale: Scale) {
  const ih = HEIGHT - PAD.top - PAD.bottom;
  return PAD.top + ih * (1 - (0 - scale.min) / scale.range);
}

function stepPath(data: ChartPoint[], scale: Scale) {
  return data
    .map((item, i) => {
      const p = pt(i, item.value, data, scale);
      return i === 0 ? `M ${p.x} ${p.y}` : `H ${p.x} V ${p.y}`;
    })
    .join(" ");
}

function areaPath(data: ChartPoint[], scale: Scale) {
  if (data.length === 0) return "";
  const points = data.map((item, i) => pt(i, item.value, data, scale));
  const baseY = zeroY(scale);
  return `${stepPath(data, scale)} L ${points[points.length - 1].x} ${baseY} H ${points[0].x} Z`;
}

function fmtTick(v: number) {
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(1)}k`;
  return `$${v.toFixed(v % 1 === 0 ? 0 : 2)}`;
}

interface ChartAreaStepProps {
  data: ChartPoint[];
  title?: string;
  subtitle?: string;
}

export default function ChartAreaStep({
  data,
  title = "Performance",
  subtitle = "Step Area Chart",
}: ChartAreaStepProps) {
  const [activeIndex, setActiveIndex] = React.useState(data.length - 1);

  React.useEffect(() => {
    setActiveIndex(data.length - 1);
  }, [data.length]);

  const scale = makeScale(data);
  const active = data[activeIndex];
  const activePoint = active ? pt(activeIndex, active.value, data, scale) : null;
  const z = zeroY(scale);
  const hasNegative = scale.min < 0;

  const yTicks = Array.from({ length: 5 }, (_, i) => {
    return scale.min + (scale.range / 4) * i;
  });

  // Positive PnL → blue, negative → red
  const lineColor = (active?.value ?? 0) >= 0 ? "#0b7bff" : "#f87171";
  const fillColor = (active?.value ?? 0) >= 0 ? "#0b7bff" : "#f87171";

  return (
    <div className="w-full rounded-none border-[3px] border-[rgba(243,242,238,0.12)] bg-[#0B0B0D] p-4 text-[#F3F2EE] shadow-[4px_4px_0_0_#0b7bff]">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-[#8B8D91] font-mono">{title}</p>
          <h3 className="mt-1 text-sm font-bold font-mono">{subtitle}</h3>
        </div>
        {active && (
          <div className="border-[2px] border-[rgba(243,242,238,0.12)] bg-[#1A1A1E] px-3 py-2 text-right text-[10px] leading-relaxed">
            <span className="block text-[#8B8D91] font-mono">{active.label}</span>
            <span
              className="font-mono font-bold"
              style={{ color: active.value >= 0 ? "#0b7bff" : "#f87171" }}
            >
              {active.value >= 0 ? "+" : ""}${active.value.toFixed(2)}
            </span>
          </div>
        )}
      </div>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-auto w-full overflow-visible"
        role="img"
        aria-label="Step area chart"
      >
        <defs>
          <pattern id="pixel-grid-dark" width="16" height="16" patternUnits="userSpaceOnUse">
            <path d="M 16 0 L 0 0 0 16" fill="none" stroke="rgba(243,242,238,0.04)" strokeWidth="2" />
          </pattern>
          <linearGradient id="area-gradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={fillColor} stopOpacity="0.25" />
            <stop offset="100%" stopColor={fillColor} stopOpacity="0.02" />
          </linearGradient>
        </defs>

        <rect
          x={PAD.left} y={PAD.top}
          width={WIDTH - PAD.left - PAD.right}
          height={HEIGHT - PAD.top - PAD.bottom}
          fill="url(#pixel-grid-dark)"
        />

        {/* Y axis ticks */}
        {yTicks.map((tick, i) => {
          const y = pt(0, tick, data, scale).y;
          return (
            <g key={i}>
              <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y} y2={y}
                stroke="rgba(243,242,238,0.07)" strokeDasharray="6 6" />
              <text x={PAD.left - 6} y={y + 4} textAnchor="end" fontSize="9" fill="#8B8D91">
                {fmtTick(tick)}
              </text>
            </g>
          );
        })}

        {/* Zero baseline */}
        {hasNegative && (
          <line
            x1={PAD.left} x2={WIDTH - PAD.right}
            y1={z} y2={z}
            stroke="rgba(243,242,238,0.25)" strokeWidth="1.5" strokeDasharray="4 4"
          />
        )}

        <path d={areaPath(data, scale)} fill="url(#area-gradient)" />
        <path
          d={stepPath(data, scale)}
          fill="none"
          stroke={lineColor}
          strokeWidth="2.5"
          strokeLinejoin="miter"
          strokeLinecap="square"
        />

        {/* Hit-targets + dots */}
        {data.map((item, index) => {
          const p = pt(index, item.value, data, scale);
          const isActive = index === activeIndex;
          const dotColor = item.value >= 0 ? "#0b7bff" : "#f87171";
          return (
            <g
              key={item.label}
              onMouseEnter={() => setActiveIndex(index)}
              onFocus={() => setActiveIndex(index)}
              tabIndex={0}
              className="cursor-pointer outline-none"
            >
              <line x1={p.x} x2={p.x} y1={PAD.top} y2={HEIGHT - PAD.bottom}
                stroke="transparent" strokeWidth="40" />
              <rect
                x={p.x - 5} y={p.y - 5} width="10" height="10"
                fill={isActive ? dotColor : "#1A1A1E"}
                stroke={isActive ? dotColor : "rgba(243,242,238,0.3)"}
                strokeWidth="2"
              />
            </g>
          );
        })}

        {/* X labels — thin out when many points to avoid crowding */}
        {(() => {
          const step = data.length <= 10 ? 1
            : data.length <= 30 ? Math.ceil(data.length / 8)
            : Math.ceil(data.length / 6);
          return data.map((item, index) => {
            if (index % step !== 0 && index !== data.length - 1) return null;
            const p = pt(index, item.value, data, scale);
            return (
              <text key={item.label} x={p.x} y={HEIGHT - 16}
                textAnchor="middle" fontSize="9" fill="#8B8D91">
                {item.label}
              </text>
            );
          });
        })()}

        {/* Tooltip — flips below the point when near the top */}
        {activePoint && active && (() => {
          const tipH = 42;
          const chartMidY = PAD.top + (HEIGHT - PAD.top - PAD.bottom) / 2;
          const tipY = activePoint.y < chartMidY
            ? activePoint.y + 10          // point in upper half → tooltip below
            : Math.max(activePoint.y - tipH - 10, PAD.top); // lower half → above
          const tipX = Math.min(Math.max(activePoint.x - 74, PAD.left), WIDTH - PAD.right - 148);
          return (
          <g transform={`translate(${tipX},${tipY})`}>
            <rect width="148" height={tipH} rx="2" fill="#0B0B0D"
              stroke="rgba(243,242,238,0.2)" strokeWidth="1.5" />
            <text x="10" y="16" fontSize="10" fill="#8B8D91" fontFamily="monospace">{active.label}</text>
            <text x="10" y="30" fontSize="10" fontFamily="monospace"
              fill={active.value >= 0 ? "#0b7bff" : "#f87171"}>
              P&L: {active.value >= 0 ? "+" : ""}${active.value.toFixed(2)}
            </text>
          </g>
          );
        })()}
      </svg>
    </div>
  );
}
