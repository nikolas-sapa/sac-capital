import * as React from "react";

type ChartPoint = { label: string; value: number };

const WIDTH = 720;
const HEIGHT = 360;
const PAD = { top: 28, right: 28, bottom: 48, left: 46 };

function pt(index: number, value: number, data: ChartPoint[], maxValue: number) {
  const iw = WIDTH - PAD.left - PAD.right;
  const ih = HEIGHT - PAD.top - PAD.bottom;
  return {
    x: PAD.left + (iw / Math.max(data.length - 1, 1)) * index,
    y: PAD.top + ih - (value / maxValue) * ih,
  };
}

function stepPath(data: ChartPoint[], maxValue: number) {
  return data
    .map((item, i) => {
      const p = pt(i, item.value, data, maxValue);
      return i === 0 ? `M ${p.x} ${p.y}` : `H ${p.x} V ${p.y}`;
    })
    .join(" ");
}

function areaPath(data: ChartPoint[], maxValue: number) {
  const points = data.map((item, i) => pt(i, item.value, data, maxValue));
  const baseY = HEIGHT - PAD.bottom;
  return `${stepPath(data, maxValue)} L ${points[points.length - 1].x} ${baseY} H ${points[0].x} Z`;
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
  const [activeIndex, setActiveIndex] = React.useState(Math.min(1, data.length - 1));
  const maxValue = Math.max(...data.map((d) => d.value), 1) * 1.2;
  const active = data[activeIndex];
  const activePoint = active ? pt(activeIndex, active.value, data, maxValue) : null;

  const yTicks = Array.from({ length: 5 }, (_, i) => Math.round((maxValue / 4) * i));

  return (
    <div className="w-full rounded-none border-[3px] border-[rgba(243,242,238,0.12)] bg-[#0B0B0D] p-4 text-[#F3F2EE] shadow-[4px_4px_0_0_#E55A1C]">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-[#8B8D91] font-mono">{title}</p>
          <h3 className="mt-1 text-sm font-bold font-mono">{subtitle}</h3>
        </div>
        {active && (
          <div className="border-[2px] border-[rgba(243,242,238,0.12)] bg-[#1A1A1E] px-3 py-2 text-right text-[10px] leading-relaxed">
            <span className="block text-[#8B8D91] font-mono">{active.label}</span>
            <span className="text-[#E55A1C] font-mono font-bold">{active.value}</span>
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
        </defs>

        <rect
          x={PAD.left} y={PAD.top}
          width={WIDTH - PAD.left - PAD.right}
          height={HEIGHT - PAD.top - PAD.bottom}
          fill="url(#pixel-grid-dark)"
        />

        {yTicks.map((tick) => {
          const y = pt(0, tick, data, maxValue).y;
          return (
            <g key={tick}>
              <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y} y2={y} stroke="rgba(243,242,238,0.08)" strokeDasharray="8 8" />
              <text x={PAD.left - 14} y={y + 4} textAnchor="end" fontSize="10" fill="#8B8D91">{tick}</text>
            </g>
          );
        })}

        <path d={areaPath(data, maxValue)} fill="#E55A1C" opacity="0.15" />
        <path d={stepPath(data, maxValue)} fill="none" stroke="#E55A1C" strokeWidth="3" strokeLinejoin="miter" strokeLinecap="square" />

        {data.map((item, index) => {
          const p = pt(index, item.value, data, maxValue);
          const isActive = index === activeIndex;
          return (
            <g
              key={item.label}
              onMouseEnter={() => setActiveIndex(index)}
              onFocus={() => setActiveIndex(index)}
              tabIndex={0}
              className="cursor-pointer outline-none"
            >
              <line x1={p.x} x2={p.x} y1={PAD.top} y2={HEIGHT - PAD.bottom} stroke="transparent" strokeWidth="46" />
              <rect
                x={p.x - 7} y={p.y - 7} width="14" height="14"
                fill={isActive ? "#E55A1C" : "#1A1A1E"}
                stroke={isActive ? "#E55A1C" : "rgba(243,242,238,0.3)"}
                strokeWidth="2"
              />
            </g>
          );
        })}

        {data.map((item, index) => {
          const p = pt(index, item.value, data, maxValue);
          return (
            <text key={item.label} x={p.x} y={HEIGHT - 18} textAnchor="middle" fontSize="10" fill="#8B8D91">
              {item.label}
            </text>
          );
        })}

        {activePoint && active && (
          <g transform={`translate(${Math.min(activePoint.x + 14, WIDTH - 170)} ${Math.max(activePoint.y - 62, 18)})`}>
            <rect width="152" height="46" fill="#0B0B0D" stroke="rgba(243,242,238,0.2)" strokeWidth="2" />
            <text x="12" y="18" fontSize="10" fill="#8B8D91" fontFamily="monospace">{active.label}</text>
            <text x="12" y="34" fontSize="10" fill="#E55A1C" fontFamily="monospace">Value: {active.value}</text>
          </g>
        )}
      </svg>
    </div>
  );
}
