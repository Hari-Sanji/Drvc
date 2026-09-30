import { memo, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Background, Controls, Handle, Position, ReactFlow, ReactFlowProvider, useReactFlow } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from 'd3-force'
import { Briefcase, Building2, CalendarDays, FileText, Fingerprint, Image as ImageIcon, MapPin, Network, User, X } from 'lucide-react'
import { Empty } from '../ui'

export const NODE_TYPES = {
  case: { label: 'Case', color: '#d97745', icon: Briefcase },
  document: { label: 'Document', color: '#e0b089', icon: FileText },
  image: { label: 'Image', color: '#f472b6', icon: ImageIcon },
  person: { label: 'Person', color: '#c084fc', icon: User },
  organization: { label: 'Organization', color: '#c8b6a6', icon: Building2 },
  location: { label: 'Location', color: '#34d399', icon: MapPin },
  identifier: { label: 'Identifier', color: '#e8c39e', icon: Fingerprint },
  event: { label: 'Event', color: '#fbbf24', icon: CalendarDays },
}
const CENTER = { top: '50%', left: '50%', transform: 'translate(-50%,-50%)', width: 1, height: 1, minWidth: 0, minHeight: 0, border: 0, background: 'transparent' }

const GNode = memo(({ data }) => {
  const t = NODE_TYPES[data.kind] || NODE_TYPES.document
  const I = t.icon
  return (
    <div className={`gnode ${data.kind === 'case' ? 'case' : ''} ${data.flag === 'conflict' ? 'conflict' : ''} ${data.selected ? 'selected' : ''} ${data.dim ? 'dim' : ''}`}
      style={{ animationDelay: `${data.delay || 0}ms` }} title={`${t.label}: ${data.label}${data.sub ? ` — ${data.sub}` : ''}`}>
      <Handle type="target" position={Position.Top} style={CENTER} isConnectable={false} />
      <Handle type="source" position={Position.Bottom} style={CENTER} isConnectable={false} />
      <div className="gi" style={{ background: data.kind === 'case' ? undefined : `${t.color}22`, color: data.kind === 'case' ? '#fff' : t.color }}><I /></div>
      <div className="gl"><b>{data.label}</b>{data.sub && <span>{data.sub}</span>}</div>
    </div>
  )
})
const nodeTypes = { g: GNode }

function layout(nodes, edges) {
  const sim = nodes.map((n) => ({ id: n.id, type: n.type, ...(n.type === 'case' ? { fx: 0, fy: 0 } : {}) }))
  const idx = new Map(sim.map((n, i) => [n.id, i]))
  const links = edges.filter((e) => idx.has(e.source) && idx.has(e.target)).map((e) => ({ source: e.source, target: e.target, type: e.type }))
  // deterministic starting positions: records on an inner ring, entities outside
  const recs = sim.filter((n) => n.type === 'document' || n.type === 'image')
  recs.forEach((n, i) => { const a = (i / recs.length) * Math.PI * 2; n.x = Math.cos(a) * 260; n.y = Math.sin(a) * 260 })
  sim.forEach((n, i) => { if (n.x == null) { const a = i * 2.4; n.x = Math.cos(a) * 520; n.y = Math.sin(a) * 520 } })
  forceSimulation(sim)
    .force('link', forceLink(links).id((d) => d.id).distance((l) => ({ contains: 210, relationship: 200, mentions: 120, event: 120 }[l.type] || 140)).strength((l) => (l.type === 'relationship' ? 0.15 : 0.6)))
    .force('charge', forceManyBody().strength(-520).distanceMax(700))
    .force('collide', forceCollide(88))
    .force('x', forceX(0).strength(0.06)).force('y', forceY(0).strength(0.08))
    .stop().tick(320)
  return new Map(sim.map((n) => [n.id, { x: n.x, y: n.y }]))
}

function GraphInner({ data }) {
  const [hidden, setHidden] = useState(new Set())
  const [shown, setShown] = useState(0)
  const [sel, setSel] = useState(null)
  const { fitView } = useReactFlow()

  const ordered = useMemo(() => {
    const rank = { case: 0, document: 1, image: 1, person: 2, identifier: 3, organization: 4, location: 5, event: 6 }
    return [...data.nodes].sort((a, b) => (rank[a.type] ?? 9) - (rank[b.type] ?? 9))
  }, [data])
  const pos = useMemo(() => layout(data.nodes, data.edges), [data])

  useEffect(() => {
    setShown(0)
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduce) { setShown(ordered.length); return }
    let n = 0
    const t = setInterval(() => { n += 1; setShown(n); if (n >= ordered.length) clearInterval(t) }, 55)
    return () => clearInterval(t)
  }, [ordered])
  const revealed = shown >= ordered.length
  useEffect(() => { const t = setTimeout(() => fitView({ padding: 0.06, duration: 700, maxZoom: 1.1 }), revealed ? 120 : 300); return () => clearTimeout(t) }, [data, fitView, revealed])

  const visibleIds = useMemo(() => new Set(ordered.slice(0, shown).filter((n) => !hidden.has(n.type)).map((n) => n.id)), [ordered, shown, hidden])
  const neighbors = useMemo(() => {
    if (!sel || sel.kind !== 'node') return null
    const s = new Set([sel.id])
    data.edges.forEach((e) => { if (e.source === sel.id) s.add(e.target); if (e.target === sel.id) s.add(e.source) })
    return s
  }, [sel, data])

  const rfNodes = useMemo(() => ordered.filter((n) => visibleIds.has(n.id)).map((n) => ({
    id: n.id, type: 'g', position: { x: pos.get(n.id).x - 80, y: pos.get(n.id).y - 22 },
    data: { kind: n.type, label: n.label, sub: n.sub, flag: n.flag, selected: sel?.id === n.id, dim: neighbors && !neighbors.has(n.id) },
    draggable: true,
  })), [ordered, visibleIds, pos, sel, neighbors])

  const rfEdges = useMemo(() => data.edges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target)).map((e) => {
    const rel = e.type === 'relationship'
    const active = !neighbors || (neighbors.has(e.source) && neighbors.has(e.target))
    const strong = rel && e.score >= 0.75
    return {
      id: e.id, source: e.source, target: e.target, type: 'straight', animated: rel,
      label: rel ? `${Math.round(e.score * 100)}%` : undefined,
      labelStyle: { fill: 'var(--text)', fontSize: 10.5, fontWeight: 600 },
      labelBgStyle: { fill: 'var(--surface-solid)' }, labelBgPadding: [5, 3], labelBgBorderRadius: 6,
      className: rel ? '' : 'edge-draw',
      style: {
        stroke: rel ? (strong ? '#e8c39e' : '#d97745') : e.type === 'contains' ? 'rgba(217,119,69,.45)' : 'rgba(232,200,170,.28)',
        strokeWidth: rel ? 1.5 + e.score * 2 : 1, opacity: active ? 1 : 0.12,
      },
      data: e,
    }
  }), [data, visibleIds, neighbors])

  const counts = useMemo(() => data.nodes.reduce((a, n) => ({ ...a, [n.type]: (a[n.type] || 0) + 1 }), {}), [data])
  const selNode = sel?.kind === 'node' ? data.nodes.find((n) => n.id === sel.id) : null
  const selEdge = sel?.kind === 'edge' ? data.edges.find((e) => e.id === sel.id) : null
  const nodeLabel = (id) => data.nodes.find((n) => n.id === id)
  return (
    <div>
      <div className="row wrap between" style={{ marginBottom: 12 }}>
        <div className="legend" role="group" aria-label="Toggle node types">
          {Object.entries(NODE_TYPES).filter(([k]) => counts[k]).map(([k, t]) => (
            <button key={k} className={hidden.has(k) ? 'off' : ''} aria-pressed={!hidden.has(k)}
              onClick={() => setHidden((h) => { const n = new Set(h); n.has(k) ? n.delete(k) : n.add(k); return n })}>
              <i style={{ background: t.color }} />{t.label} · {counts[k]}
            </button>
          ))}
        </div>
        <div className="row tiny faint" style={{ gap: 14 }}>
          <span className="row" style={{ gap: 6 }}><i style={{ width: 18, height: 3, background: '#e8c39e', borderRadius: 2, display: 'inline-block' }} />Likely Related (≥75%)</span>
          <span className="row" style={{ gap: 6 }}><i style={{ width: 18, height: 3, background: '#d97745', borderRadius: 2, display: 'inline-block' }} />Possible Match / Signal</span>
        </div>
      </div>
      <div className="card graph-wrap">
        <ReactFlow nodes={rfNodes} edges={rfEdges} nodeTypes={nodeTypes} minZoom={0.2} maxZoom={2}
          onNodeClick={(_, n) => setSel({ kind: 'node', id: n.id })} onEdgeClick={(_, e) => setSel({ kind: 'edge', id: e.id })}
          onPaneClick={() => setSel(null)} proOptions={{ hideAttribution: true }} fitView>
          <Background gap={28} size={1} color="rgba(232,200,170,.15)" />
          <Controls showInteractive={false} />
        </ReactFlow>
        {(selNode || selEdge) && (
          <div className="card graph-side" style={{ background: 'var(--surface-solid)' }}>
            <div className="card-head" style={{ padding: '12px 14px' }}>
              <h3 style={{ fontSize: 14 }}>{selNode ? NODE_TYPES[selNode.type]?.label : 'Relationship signal'}</h3>
              <button className="btn ghost icon sm" aria-label="Close details" onClick={() => setSel(null)}><X /></button>
            </div>
            <div className="card-body stack" style={{ padding: 14, gap: 10 }}>
              {selNode && <>
                <div><b>{selNode.label}</b>{selNode.sub && <div className="small muted">{selNode.sub}</div>}</div>
                {selNode.record_id && <Link className="btn sm" to={`/app/records/${selNode.record_id}`}>Open record</Link>}
                {selNode.shared != null && <p className="small muted">Mentioned in <b>{selNode.shared}</b> record{selNode.shared > 1 ? 's' : ''}{selNode.shared > 1 ? ' — a shared entity is a relationship signal.' : '.'}</p>}
                {selNode.flag === 'conflict' && <span className="badge b-red">Potential inconsistency involves this record</span>}
                <p className="tiny faint">{neighbors ? neighbors.size - 1 : 0} direct connections highlighted.</p>
              </>}
              {selEdge && <>
                <div className="small"><b>{nodeLabel(selEdge.source)?.sub}</b> ↔ <b>{nodeLabel(selEdge.target)?.sub}</b></div>
                <div className="row wrap"><span className={`badge ${selEdge.score >= 0.75 ? 'b-cyan' : 'b-violet'}`}>{selEdge.label}</span><span className="badge b-neutral">{Math.round((selEdge.score || 0) * 100)}% signal strength</span></div>
                {selEdge.evidence && <div className="stack" style={{ gap: 6 }}>
                  <span className="label">Evidence</span>
                  {selEdge.evidence.map((ev, i) => <div key={i} className="chip" style={{ display: 'block' }}><b className="tiny" style={{ color: 'var(--violet-2)' }}>{ev.type}</b><div className="small">{ev.value}</div><div className="tiny faint">{ev.detail}</div></div>)}
                </div>}
                <p className="tiny faint">Relationship signals are probabilistic and never certain.</p>
              </>}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Graph({ data }) {
  if (!data || data.nodes.filter((n) => n.type === 'document' || n.type === 'image').length === 0) {
    return <Empty icon={Network} title="No relationship signals yet">No relationship signals detected between the current records. Upload two or more records to build the relationship map.</Empty>
  }
  return <ReactFlowProvider><GraphInner data={data} /></ReactFlowProvider>
}
