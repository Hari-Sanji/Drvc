import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { CheckCircle2, Compass, Minimize2, Play, Sparkles, X } from 'lucide-react'
import { api } from './api'
import { useAuth } from './auth'
import { Button, useToast } from './ui'

const DemoCtx = createContext(null)
const KEY = 'drcv-demo-guide'

function load() {
  try { return JSON.parse(localStorage.getItem(KEY)) || {} } catch { return {} }
}
function save(v) {
  try { localStorage.setItem(KEY, JSON.stringify(v)) } catch { /* ignore */ }
}

export function DemoProvider({ children }) {
  const [state, setState] = useState(() => ({ open: false, min: false, done: [], caseId: null, recordId: null, ...load() }))
  const navigate = useNavigate()
  const toast = useToast()
  const { user } = useAuth()

  useEffect(() => save(state), [state])
  useEffect(() => { if (!user) setState((s) => ({ ...s, open: false })) }, [user])

  const launch = useCallback(async () => {
    try {
      const r = await api.post('/demo/launch')
      let recordId = null
      try {
        const ov = await api.get(`/cases/${r.case_id}/overview`)
        recordId = (ov.records.find((x) => x.doc_type === 'Degree Certificate') || ov.records[0])?.id || null
      } catch { /* ignore */ }
      setState((s) => ({ ...s, open: true, min: false, caseId: r.case_id, recordId, done: [] }))
      navigate(`/app/cases/${r.case_id}${r.started ? '?pipeline=1' : ''}`)
      if (!r.started) toast('Opened the demo case in read-only mode for your role.', 'info')
    } catch (e) {
      toast(e.message, 'error')
    }
  }, [navigate, toast])

  const markDone = useCallback((key) => setState((s) => (s.done.includes(key) ? s : { ...s, done: [...s.done, key] })), [])
  const value = useMemo(() => ({ ...state, launch, markDone, setGuide: (p) => setState((s) => ({ ...s, ...p })) }), [state, launch, markDone])
  return <DemoCtx.Provider value={value}>{children}{user && <DemoGuide />}</DemoCtx.Provider>
}
export const useDemo = () => useContext(DemoCtx)

export function DemoGuide() {
  const demo = useDemo()
  const loc = useLocation()
  const navigate = useNavigate()
  const { caseId: c, recordId: r } = demo
  const steps = useMemo(() => [
    { k: 'case', label: 'Open Case', to: `/app/cases/${c}`, match: (p, h) => p === `/app/cases/${c}` || p === `/app/cases/${c}/overview` },
    { k: 'records', label: 'View Records', to: `/app/cases/${c}/records`, match: (p) => p === `/app/cases/${c}/records` },
    { k: 'record', label: 'Open Record', to: `/app/records/${r}`, match: (p) => p === `/app/records/${r}` },
    { k: 'hash', label: 'View SHA-256', to: `/app/records/${r}#integrity`, match: (p, h) => p === `/app/records/${r}` && h === '#integrity' },
    { k: 'extract', label: 'View Extracted Information', to: `/app/records/${r}#extracted`, match: (p, h) => p === `/app/records/${r}` && h === '#extracted' },
    { k: 'graph', label: 'Open Relationship Graph', to: `/app/cases/${c}/relationships`, match: (p) => p === `/app/cases/${c}/relationships` },
    { k: 'timeline', label: 'Open Timeline', to: `/app/cases/${c}/timeline`, match: (p) => p === `/app/cases/${c}/timeline` },
    { k: 'conflict', label: 'View Conflict', to: `/app/cases/${c}/conflicts`, match: (p) => p === `/app/cases/${c}/conflicts` },
    { k: 'review', label: 'Review Conflict', to: `/app/cases/${c}/review`, match: () => false },
    { k: 'report', label: 'Generate Report', to: `/app/cases/${c}/reports`, match: () => false },
  ], [c, r])

  const { markDone } = demo
  useEffect(() => {
    if (!c) return
    for (const s of steps) if (s.match(loc.pathname, loc.hash)) markDone(s.k)
  }, [loc.pathname, loc.hash, steps, c, markDone])

  if (!c) return null
  if (!demo.open) return null
  const next = steps.find((s) => !demo.done.includes(s.k))
  const pct = Math.round((demo.done.length / steps.length) * 100)
  if (demo.min) {
    return (
      <div className="guide-fab">
        <Button variant="primary" icon={Compass} onClick={() => demo.setGuide({ min: false })}>Demo guide · {demo.done.length}/10</Button>
      </div>
    )
  }
  return (
    <div className="guide card glow-border" role="complementary" aria-label="Guided demo">
      <div className="card-head">
        <h3><Sparkles />Guided demo</h3>
        <div className="row" style={{ gap: 2 }}>
          <button className="btn ghost icon sm" aria-label="Minimize guide" onClick={() => demo.setGuide({ min: true })}><Minimize2 /></button>
          <button className="btn ghost icon sm" aria-label="Close guide" onClick={() => demo.setGuide({ open: false })}><X /></button>
        </div>
      </div>
      <div style={{ padding: '10px 16px 4px' }}>
        <div className="progress"><span style={{ width: `${pct}%` }} /></div>
        <p className="tiny faint" style={{ marginTop: 6 }}>{next ? `Next: ${next.label}` : 'Tour complete — you have seen the full pipeline.'}</p>
      </div>
      <div style={{ padding: '4px 0 10px' }}>
        {steps.map((s, i) => {
          const done = demo.done.includes(s.k)
          return (
            <button key={s.k} className={`guide-step ${done ? 'done' : ''} ${next?.k === s.k ? 'next' : ''}`}
              onClick={() => navigate(s.to)}>
              <span className="gs-n">{done ? <CheckCircle2 size={13} /> : i + 1}</span>{s.label}
              {next?.k === s.k && <Play size={13} style={{ marginLeft: 'auto', color: 'var(--cyan-2)' }} />}
            </button>
          )
        })}
      </div>
    </div>
  )
}
