import type { CategoryResult } from '../types';

interface Props {
  categories: CategoryResult[];
  size?: number;
}

const LABEL_SHORT: Record<string, string> = {
  agent_access: 'Agent\nAccess',
  discoverability: 'Discover-\nability',
  structured_data: 'Structured\nData',
  content_clarity: 'Content\nClarity',
  citation_probe: 'Citation\nProbe',
};

function gradeColor(score: number): string {
  if (score >= 85) return '#5D7A3E';
  if (score >= 70) return '#64703C';
  if (score >= 55) return '#8A6A1F';
  if (score >= 40) return '#8A4F22';
  return '#8B3A2E';
}

export function RadarChart({ categories, size = 300 }: Props) {
  if (categories.length < 3) return null;

  const cx = size / 2;
  const cy = size / 2;
  const radius = size * 0.35;
  const labelRadius = size * 0.48;
  const n = categories.length;
  const angleStep = (2 * Math.PI) / n;
  const startAngle = -Math.PI / 2;

  function polarToXY(angle: number, r: number): [number, number] {
    return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
  }

  const rings = [0.25, 0.5, 0.75, 1.0];
  const axes = categories.map((_, i) => {
    const angle = startAngle + i * angleStep;
    return { angle, end: polarToXY(angle, radius) };
  });

  const dataPoints = categories.map((cat, i) => {
    const angle = startAngle + i * angleStep;
    const r = (cat.score / 100) * radius;
    return polarToXY(angle, r);
  });

  const dataPath = dataPoints.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ') + ' Z';

  const avgScore = Math.round(categories.reduce((sum, c) => sum + c.score, 0) / categories.length);
  const fillColor = gradeColor(avgScore);

  return (
    <div className="paper-card p-6 sm:p-10 flex justify-center">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        width={size}
        height={size}
        className="max-w-full h-auto"
        role="img"
        aria-label="Radar chart showing category scores"
      >
        {/* Grid rings */}
        {rings.map((frac) => {
          const r = frac * radius;
          const points = Array.from({ length: n }, (_, i) => {
            const angle = startAngle + i * angleStep;
            return polarToXY(angle, r);
          });
          const path = points.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ') + ' Z';
          return (
            <path key={frac} d={path} fill="none" stroke="#E5DCCB" strokeWidth="1" opacity="0.7" />
          );
        })}

        {/* Axes */}
        {axes.map((axis, i) => (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={axis.end[0]}
            y2={axis.end[1]}
            stroke="#E5DCCB"
            strokeWidth="1"
            opacity="0.5"
          />
        ))}

        {/* Data polygon */}
        <path
          d={dataPath}
          fill={fillColor}
          fillOpacity="0.15"
          stroke={fillColor}
          strokeWidth="2"
          className="animate-fade-in"
        />

        {/* Data points */}
        {dataPoints.map(([x, y], i) => {
          const cat = categories[i];
          const color = gradeColor(cat.score);
          return (
            <circle
              key={cat.id}
              cx={x}
              cy={y}
              r="4"
              fill={color}
              stroke="#FFFDF9"
              strokeWidth="2"
            />
          );
        })}

        {/* Labels */}
        {categories.map((cat, i) => {
          const angle = startAngle + i * angleStep;
          const [lx, ly] = polarToXY(angle, labelRadius);
          const lines = (LABEL_SHORT[cat.id] || cat.label).split('\n');
          const allSkipped = cat.checks.length > 0 && cat.checks.every((c) => c.status === 'skip');

          return (
            <g key={cat.id}>
              {lines.map((line, li) => (
                <text
                  key={li}
                  x={lx}
                  y={ly + li * 13 - ((lines.length - 1) * 13) / 2}
                  textAnchor="middle"
                  dominantBaseline="central"
                  className="fill-ink-500"
                  style={{ fontSize: '10px', fontFamily: 'Inter, sans-serif' }}
                >
                  {line}
                </text>
              ))}
              <text
                x={lx}
                y={ly + ((lines.length - 1) * 13) / 2 + 14}
                textAnchor="middle"
                dominantBaseline="central"
                className={allSkipped ? 'fill-ink-300' : 'fill-ink-900'}
                style={{
                  fontSize: '13px',
                  fontFamily: 'Fraunces, serif',
                  fontWeight: 500,
                }}
              >
                {allSkipped ? '—' : cat.score}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
