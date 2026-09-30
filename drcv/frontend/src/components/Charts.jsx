import { useMemo, useRef, useState } from 'react'

// Validated categorical order (dark + light surfaces): copper, plum, amber, green.
export const SERIES = ['#c2652f', '#b0457f', '#d97706', '#059669']

export function Legend({ items }) {
  return (
    <div className="row wrap" style={{ gap: 14 }}>
      {items.map(([label, color, value]) => (
        <span key={label} className="row small muted" style={{ gap: 6 }}>
          <i style={{ width: 10, height: 10, borderRadius: 3, background: color, display: 'inline-block' }} />
          {label}{value != null && <b style={{ color: 'var(--text)' }}>{value}</b>}
        </span>
      ))}
    </div>
  )
}

/** Multi-series area/line chart with crosshair tooltip. data: [{date, ...keys}] */
export function AreaChart({ data, series, height = 230 }) {
  const ref = useRef(null)
  const [hover, setHover] = useState(null)
  const W = 640, H = height, P = { l: 34, r: 12, t: 12, b: 26 }
  const max = Math.max(1, ...data.flatMap((d) => series.map((s) => d[s.key])))
  const niceMax = Math.ceil(max / 2) * 2 || 2
  const x = (i) => P.l + (i * (W - P.l - P.r)) / Math.max(1, data.length - 1)
  const y = (v) => H - P.b - (v / niceMax) * (H - P.t - P.b)
  const paths = useMemo(() => series.map((s) => {
    const pts = data.map((d, i) => [x(i), y(d[s.key])])
    const line = pts.map((p, i) => {
      if (i === 0) return `M${p[0]},${p[1]}`
      const [px, py] = pts[i - 1]
      const cx = (px + p[0]) / 2
      return `C${cx},${py} ${cx},${p[1]} ${p[0]},${p[1]}`
    }).join(' ')
    return { ...s, line, area: `${line} L${x(data.length - 1)},${H - P.b} L${x(0)},${H - P.b} Z` }
  }), [data, series]) // eslint-disable-line react-hooks/exhaustive-deps

  const onMove = (e) => {
    const r = ref.current.getBoundingClientRect()
    const px = ((e.clientX - r.left) / r.width) * W
    const i = Math.max(0, Math.min(data.length - 1, Math.round(((px - P.l) / (W - P.l - P.r)) * (data.length - 1))))
    setHover({ i, left: (x(i) / W) * r.width, top: (Math.min(...series.map((s) => y(data[i][s.key]))) / H) * r.height })
  }
  const ticks = [0, niceMax / 2, niceMax]
  return (
    <div style={{ position: 'relative' }}>
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Records processed and review actions over the last 14 days"
        onMouseMove={onMove} onMouseLeave={() => setHover(null)} style={{ display: 'block', overflow: 'visible' }}>
        <defs>
          {series.map((s) => (
            <linearGradient key={s.key} id={`ag-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor={s.color} stopOpacity=".35" /><stop offset="1" stopColor={s.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="var(--border)" strokeDasharray={t ? '3 4' : ''} />
            <text x={P.l - 8} y={y(t) + 4} textAnchor="end" fontSize="10.5" fill="var(--text-3)">{t}</text>
          </g>
        ))}
        {data.map((d, i) => (i % 2 === 0 || i === data.length - 1) && (
          <text key={d.date} x={x(i)} y={H - 6} textAnchor="middle" fontSize="10.5" fill="var(--text-3)">
            {new Date(d.date + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}
          </text>
        ))}
        {paths.map((p) => <path key={p.key + 'a'} d={p.area} fill={`url(#ag-${p.key})`} className="draw-area" />)}
        {paths.map((p) => <path key={p.key} d={p.line} fill="none" stroke={p.color} strokeWidth="2" strokeLinecap="round" className="edge-draw" style={{ strokeDasharray: 2000, strokeDashoffset: 2000, animationDuration: '1.8s' }} />)}
        {hover && (
          <g>
            <line x1={x(hover.i)} x2={x(hover.i)} y1={P.t} y2={H - P.b} stroke="var(--border-strong)" />
            {series.map((s) => <circle key={s.key} cx={x(hover.i)} cy={y(data[hover.i][s.key])} r="4.5" fill={s.color} stroke="var(--surface-solid)" strokeWidth="2" />)}
          </g>
        )}
      </svg>
      {hover && (
        <div className="chart-tip" style={{ left: hover.left, top: hover.top }}>
          <div className="tiny faint">{new Date(data[hover.i].date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}</div>
          {series.map((s) => (
            <div key={s.key} className="row small" style={{ gap: 6 }}>
              <i style={{ width: 8, height: 8, borderRadius: 2, background: s.color, display: 'inline-block' }} />
              {s.label}: <b>{data[hover.i][s.key]}</b>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** Donut with hover highlight. items: [{label, value, color}] */
export function Donut({ items, size = 180, label = 'Total' }) {
  const [hi, setHi] = useState(null)
  const total = items.reduce((a, b) => a + b.value, 0)
  const R = 70, C = 2 * Math.PI * R
  let acc = 0
  const gap = total > 0 && items.filter((i) => i.value).length > 1 ? 3 : 0
  return (
    <div className="row wrap" style={{ gap: 22, justifyContent: 'center' }}>
      <svg width={size} height={size} viewBox="0 0 180 180" role="img" aria-label={`${label}: ${items.map((i) => `${i.label} ${i.value}`).join(', ')}`}>
        <circle cx="90" cy="90" r={R} fill="none" stroke="var(--surface-3)" strokeWidth="16" />
        {total > 0 && items.map((it, idx) => {
          if (!it.value) return null
          const len = (it.value / total) * C
          const seg = (
            <circle key={it.label} className="donut-seg" cx="90" cy="90" r={R} fill="none" stroke={it.color} strokeWidth={hi === idx ? 20 : 16}
              strokeDasharray={`${Math.max(0, len - gap)} ${C}`} strokeDashoffset={-acc} transform="rotate(-90 90 90)" strokeLinecap="butt"
              style={{ opacity: hi == null || hi === idx ? 1 : 0.35, cursor: 'pointer', transition: 'stroke-width .2s, opacity .2s' }}
              onMouseEnter={() => setHi(idx)} onMouseLeave={() => setHi(null)}>
              <title>{`${it.label}: ${it.value}`}</title>
            </circle>
          )
          acc += len
          return seg
        })}
        <text x="90" y="86" textAnchor="middle" fontSize="30" fontWeight="600" fill="var(--text)">{hi != null ? items[hi].value : total}</text>
        <text x="90" y="108" textAnchor="middle" fontSize="11" fill="var(--text-3)">{hi != null ? items[hi].label : label}</text>
      </svg>
      <div className="stack" style={{ gap: 8, minWidth: 150 }}>
        {items.map((it, idx) => (
          <div key={it.label} className="row between small" style={{ gap: 18, opacity: hi == null || hi === idx ? 1 : 0.5, cursor: 'default' }}
            onMouseEnter={() => setHi(idx)} onMouseLeave={() => setHi(null)}>
            <span className="row muted" style={{ gap: 8 }}><i style={{ width: 10, height: 10, borderRadius: 3, background: it.color, display: 'inline-block' }} />{it.label}</span>
            <b>{it.value}</b>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Horizontal single-series bars. */
export function BarList({ items, color = '#e11d48' }) {
  const max = Math.max(1, ...items.map((i) => i.value))
  return (
    <div className="stack" style={{ gap: 12 }}>
      {items.map((it, i) => (
        <div key={it.label} className="bar-row" title={`${it.label}: ${it.value}`}>
          <span className="muted truncate">{it.label}</span>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${(it.value / max) * 100}%`, background: color, animationDelay: `${i * 90}ms`, minWidth: it.value ? 6 : 0 }} /></div>
          <b style={{ textAlign: 'right' }}>{it.value}</b>
        </div>
      ))}
    </div>
  )
}
