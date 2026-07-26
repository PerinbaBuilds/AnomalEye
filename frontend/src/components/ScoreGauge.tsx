import type { RiskLevel } from "../types";
import { riskColor } from "../lib/format";

/** Semicircular risk gauge (0–100) coloured by band. */
export default function ScoreGauge({
  score,
  level,
  size = 180,
}: {
  score: number;
  level: RiskLevel;
  size?: number;
}) {
  const r = size / 2 - 14;
  const cx = size / 2;
  const cy = size / 2;
  const circ = Math.PI * r; // semicircle length
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const color = riskColor[level];

  const arc = (frac: number) => {
    const a = Math.PI * (1 - frac);
    return `${cx + r * Math.cos(a)},${cy - r * Math.sin(a)}`;
  };

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size / 2 + 20}>
        <path
          d={`M ${cx - r},${cy} A ${r},${r} 0 0 1 ${cx + r},${cy}`}
          fill="none"
          stroke="#232c42"
          strokeWidth={12}
          strokeLinecap="round"
        />
        <path
          d={`M ${arc(0)} A ${r},${r} 0 0 1 ${arc(pct)}`}
          fill="none"
          stroke={color}
          strokeWidth={12}
          strokeLinecap="round"
          strokeDasharray={circ}
          style={{ transition: "stroke-dasharray 0.6s ease" }}
        />
        <text
          x={cx}
          y={cy - 6}
          textAnchor="middle"
          fontSize={34}
          fontWeight={700}
          fill="#f1f5f9"
        >
          {score.toFixed(0)}
        </text>
        <text x={cx} y={cy + 12} textAnchor="middle" fontSize={11} fill="#8a93a6">
          / 100
        </text>
      </svg>
      <span
        className="pill mt-1"
        style={{
          color,
          backgroundColor: `${color}22`,
          border: `1px solid ${color}55`,
        }}
      >
        {level.toUpperCase()} RISK
      </span>
    </div>
  );
}
