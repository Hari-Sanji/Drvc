import { useEffect, useRef, useState } from 'react'
import { CalendarRange, CheckCircle2, Fingerprint, Lock, Network, ScanSearch, ShieldCheck, Sparkles } from 'lucide-react'
import { api } from '../api'
import { Button, Modal, Principle } from '../ui'

const STAGES = [
  ['securing', 'Securing record', Lock],
  ['hashing', 'Generating hash', Fingerprint],
  ['extracting', 'Extracting information', ScanSearch],
  ['connecting', 'Connecting records', Network],
  ['timeline', 'Building timeline', CalendarRange],
  ['consistency', 'Checking consistency', ShieldCheck],
  ['complete', 'Analysis complete', CheckCircle2],
]

/** Live view of the server-side case analysis job. Polls real stage progress. */
export default function PipelineOverlay({ caseId, onClose, onComplete }) {
  const [state, setState] = useState({ stages: [], running: true })
  const [shownIdx, setShownIdx] = useState(-1)
  const done = useRef(false)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const d = await api.get(`/cases/${caseId}/analysis-status`)
        if (!alive) return
        setState(d.state || {})
        if (d.state && !d.state.running && d.state.stage === 'complete' && !done.current) { done.current = true; onComplete?.() }
      } catch { /* keep polling */ }
    }
    tick()
    const t = setInterval(tick, 450)
    return () => { alive = false; clearInterval(t) }
  }, [caseId, onComplete])

  // reveal stages one at a time so each completion is visible even when the server is fast
  const serverIdx = STAGES.findIndex(([k]) => k === state.stage)
  useEffect(() => {
    if (serverIdx > shownIdx) {
      const t = setTimeout(() => setShownIdx((i) => i + 1), shownIdx < 0 ? 0 : 420)
      return () => clearTimeout(t)
    }
  }, [serverIdx, shownIdx])

  const details = Object.fromEntries((state.stages || []).map((s) => [s.key, s.detail]))
  const finished = shownIdx === STAGES.length - 1
  return (
    <Modal title="Contextual analysis pipeline" icon={Sparkles} onClose={onClose} footer={
      finished ? <Button variant="primary" onClick={onClose}>Explore results</Button> : <Button variant="ghost" onClick={onClose}>Run in background</Button>
    }>
      {state.error && <div className="form-error" role="alert" style={{ marginBottom: 12 }}>{state.error}</div>}
      <div className="pipeline" aria-live="polite">
        {STAGES.map(([k, label, Icon], i) => {
          const st = i < shownIdx || (finished && i === shownIdx) ? 'done' : i === shownIdx ? 'active' : ''
          return (
            <div key={k}>
              <div className={`pl-step ${st}`}>
                <div className="pl-node">{st === 'done' ? <CheckCircle2 /> : <Icon />}</div>
                <div className="pl-text">
                  <b>{label}</b>
                  <div className="pl-detail">{i <= shownIdx ? (details[k] || (st === 'active' ? 'Working…' : '')) : ''}</div>
                </div>
              </div>
              {i < STAGES.length - 1 && <div className={`pl-line ${i < shownIdx ? 'done' : i === shownIdx ? 'active' : ''}`} />}
            </div>
          )
        })}
      </div>
      <div style={{ marginTop: 18 }}><Principle /></div>
    </Modal>
  )
}
