import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertOctagon, ArrowLeftRight, BadgeCheck, CheckCheck, ClipboardCheck, Eye, HelpCircle, ListChecks, MessageSquarePlus, RotateCcw, ShieldAlert, TrendingUp,
} from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import { useDemo } from '../demo'
import { Button, Modal, StatusBadge, fmtDateTime, timeAgo, useToast } from '../ui'

export const UNRESOLVED = ['requires_review', 'escalated']

const ACTIONS = [
  { key: 'mark_reviewed', label: 'Mark as Reviewed', icon: Eye, variant: '', perm: 'conflict:review', needNote: false },
  { key: 'accept', label: 'Accept Explanation', icon: BadgeCheck, variant: 'success', perm: 'conflict:review', needNote: true },
  { key: 'resolve', label: 'Resolve', icon: CheckCheck, variant: 'primary', perm: 'conflict:review', needNote: true },
  { key: 'escalate', label: 'Escalate', icon: TrendingUp, variant: 'danger', perm: 'conflict:review', needNote: true },
  { key: 'note', label: 'Add Note', icon: MessageSquarePlus, variant: '', perm: 'review:note', needNote: true },
]

export function ReviewDialog({ conflict, onClose, onDone, initial }) {
  const { can } = useAuth()
  const toast = useToast()
  const demo = useDemo()
  const [action, setAction] = useState(initial || (can('conflict:review') ? 'resolve' : 'note'))
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [history, setHistory] = useState(null)
  const actions = ACTIONS.filter((a) => can(a.perm))
  if (can('conflict:review') && !UNRESOLVED.includes(conflict.status)) actions.push({ key: 'reopen', label: 'Reopen', icon: RotateCcw, variant: 'warn', perm: 'conflict:review', needNote: false })
  const cur = actions.find((a) => a.key === action) || actions[0]

  useEffect(() => { api.get(`/conflicts/${conflict.id}`).then((d) => setHistory(d.history)).catch(() => setHistory([])) }, [conflict.id])

  const submit = async () => {
    if (cur.needNote && note.trim().length < 3) { setErr('Please provide a reason or note (at least 3 characters).'); return }
    setBusy(true); setErr('')
    try {
      const d = await api.post(`/conflicts/${conflict.id}/review`, { action: cur.key, note })
      toast(cur.key === 'note' ? 'Note added to the review record' : `${conflict.type}: ${d.status_label}`, 'success')
      if (cur.key !== 'note' && demo?.caseId === conflict.case_id) demo.markDone('review')
      onDone?.(d)
      onClose()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <Modal title="Human review" icon={ClipboardCheck} onClose={onClose} size="wide" footer={<>
      <Button variant="ghost" onClick={onClose}>Cancel</Button>
      <Button variant={cur.variant === 'danger' ? 'danger' : 'primary'} icon={cur.icon} loading={busy} onClick={submit}>{cur.label}</Button>
    </>}>
      <div className="stack" style={{ gap: 16 }}>
        <div className="row wrap between">
          <div><div className="label">Potential inconsistency</div><h3 style={{ fontSize: 17 }}>{conflict.type} · <span className="muted" style={{ fontWeight: 500 }}>{conflict.field}</span></h3></div>
          <StatusBadge kind="conflict" status={conflict.status} />
        </div>
        <ConflictSides c={conflict} />
        <p className="small muted">{conflict.explanation}</p>
        <div className="field">
          <span className="label">Decision</span>
          <div className="row wrap" role="radiogroup" aria-label="Review action">
            {actions.map((a) => (
              <Button key={a.key} size="sm" icon={a.icon} variant={action === a.key ? 'primary' : ''} role="radio" aria-checked={action === a.key} onClick={() => setAction(a.key)}>{a.label}</Button>
            ))}
          </div>
          {!can('conflict:review') && <p className="tiny faint">Your role can add notes. Review decisions are made by Reviewers and Admins.</p>}
        </div>
        <div className="field">
          <label htmlFor="rv-note">{cur.needNote ? 'Reason / note (required)' : 'Note (optional)'}</label>
          <textarea id="rv-note" className="textarea" value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)}
            placeholder={cur.key === 'resolve' ? 'e.g. Supporting document confirmed the later date.' : cur.key === 'escalate' ? 'e.g. Identifier mismatch needs confirmation from the issuing university.' : 'Add context for the audit trail…'} />
          {err && <div className="form-error" role="alert"><ShieldAlert size={14} />{err}</div>}
        </div>
        <div>
          <div className="label" style={{ marginBottom: 8 }}>Review history</div>
          {history === null ? <span className="small faint">Loading…</span> : history.length === 0 ? <span className="small faint">No review actions yet.</span> : (
            <div className="stack" style={{ gap: 8 }}>
              {history.map((h) => (
                <div key={h.id} className="chip" style={{ display: 'block' }}>
                  <div className="row between small"><b>{h.user} <span className="faint" style={{ fontWeight: 500 }}>· {h.role}</span></b><span className="tiny faint">{fmtDateTime(h.at)}</span></div>
                  <div className="small">{h.action.replace('_', ' ')}{h.from !== h.to && <span className="faint"> · {h.from_label} → {h.to_label}</span>}</div>
                  {h.note && <div className="small muted">“{h.note}”</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}

function Quote({ q }) {
  if (!q?.quote) return null
  const i = q.value ? q.quote.indexOf(q.value) : -1
  return (
    <div className="quote">
      <span className="tiny faint">{q.label ? `“${q.label}” ` : ''}source text</span>
      <code>{i >= 0 ? <>{q.quote.slice(0, i)}<mark>{q.value}</mark>{q.quote.slice(i + q.value.length)}</> : q.quote}</code>
    </div>
  )
}

export function WhyFlagged({ c }) {
  const ev = c.evidence
  if (!ev) return null
  return (
    <details className="why">
      <summary><HelpCircle size={15} />Why was this flagged?</summary>
      <div className="why-body">
        {ev.rule && <div className="tiny faint" style={{ marginBottom: 8 }}>Rule: {ev.rule}</div>}
        <ul>{(ev.reasons || []).map((r, i) => <li key={i}>{r}</li>)}</ul>
        <div className="grid g2" style={{ gap: 10, marginTop: 10 }}>
          <Quote q={ev.a} /><Quote q={ev.b} />
        </div>
        <p className="tiny faint" style={{ marginTop: 10 }}>Flagged automatically by a consistency rule. It is a signal for review, not a finding of fraud.</p>
      </div>
    </details>
  )
}

export function useSelection() {
  const [sel, setSel] = useState([])
  const toggle = (id, on) => setSel((xs) => (on ? [...new Set([...xs, id])] : xs.filter((x) => x !== id)))
  return { sel, toggle, clear: () => setSel([]), setSel }
}

export function BulkBar({ selected, onClear, onDone }) {
  const toast = useToast()
  const [action, setAction] = useState('resolve')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  if (!selected.length) return null
  const needNote = ['resolve', 'accept', 'escalate'].includes(action)
  const run = async () => {
    if (needNote && note.trim().length < 3) { toast('Please give a reason — it is recorded for every selected item.', 'warn'); return }
    setBusy(true)
    try {
      const r = await api.post('/conflicts/bulk-review', { ids: selected, action, note })
      toast(`${r.updated.length} item${r.updated.length === 1 ? '' : 's'} → ${r.status_label}${r.skipped.length ? ` · ${r.skipped.length} skipped` : ''}`, 'success')
      setNote(''); onDone?.()
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  return (
    <div className="bulk-bar card" role="region" aria-label="Bulk review">
      <b className="small">{selected.length} selected</b>
      <select className="select" style={{ width: 'auto', height: 34 }} aria-label="Bulk action" value={action} onChange={(e) => setAction(e.target.value)}>
        <option value="resolve">Resolve</option><option value="accept">Accept explanation</option>
        <option value="mark_reviewed">Mark as reviewed</option><option value="escalate">Escalate</option>
      </select>
      <input className="input grow" style={{ height: 34, minWidth: 180 }} placeholder={needNote ? 'Reason (required, applied to all)' : 'Note (optional)'}
        aria-label="Reason for bulk action" value={note} onChange={(e) => setNote(e.target.value)} />
      <Button size="sm" variant="primary" icon={ListChecks} loading={busy} onClick={run}>Apply to {selected.length}</Button>
      <Button size="sm" variant="ghost" onClick={onClear}>Clear</Button>
    </div>
  )
}

export function ConflictSides({ c }) {
  const same = c.record_a.id === c.record_b.id
  return (
    <div className="vs">
      <div className="side">
        <div className="tiny faint">{same ? 'Recorded' : 'Record A'} · {c.record_a.doc_type}</div>
        <div className="val">{c.record_a.value}</div>
        <Link to={`/app/records/${c.record_a.id}`}>{c.record_a.filename}</Link>
      </div>
      <div className="vs-mid" aria-hidden><ArrowLeftRight /></div>
      <div className="side">
        <div className="tiny faint">{same ? 'Compared with' : 'Record B'} · {c.record_b.doc_type}</div>
        <div className="val">{c.record_b.value}</div>
        <Link to={`/app/records/${c.record_b.id}`}>{c.record_b.filename}</Link>
      </div>
    </div>
  )
}

export function ConflictCard({ c, onChanged, showCase, delay = 0, selected, onSelect }) {
  const { can } = useAuth()
  const [open, setOpen] = useState(null)
  const unresolved = UNRESOLVED.includes(c.status)
  return (
    <article className={`card conflict ${unresolved ? (c.status === 'escalated' ? 'esc' : '') : 'done'} `} style={{ animation: `page-in .45s ${delay}ms both${c.status === 'requires_review' ? ', pulse-card 2.6s ease-in-out infinite' : ''}` }}>
      <div className="row between wrap" style={{ gap: 10 }}>
        <div className="row" style={{ gap: 12 }}>
          {onSelect && can('conflict:review') && unresolved && (
            <input type="checkbox" className="bulk-check" checked={!!selected} onChange={(e) => onSelect(c.id, e.target.checked)}
              aria-label={`Select ${c.type} for bulk review`} />
          )}
          <div className="stat-icon ic-red" style={{ width: 36, height: 36, borderRadius: 11, display: 'grid', placeItems: 'center' }}><AlertOctagon size={18} /></div>
          <div>
            <div className="tiny faint" style={{ letterSpacing: '.12em', textTransform: 'uppercase', fontWeight: 600 }}>Potential inconsistency</div>
            <h3 style={{ fontSize: 16 }}>{c.type}</h3>
          </div>
        </div>
        <div className="row wrap">
          <span className={`badge ${c.severity === 'high' ? 'b-red' : 'b-amber'}`}>{c.severity} priority</span>
          <StatusBadge kind="conflict" status={c.status} />
        </div>
      </div>
      <div className="small muted" style={{ marginTop: 8 }}>{c.field}{showCase && c.case && <> · <Link to={`/app/cases/${c.case.id}/conflicts`}>{c.case.code}</Link></>} · detected {timeAgo(c.detected_at)}</div>
      <ConflictSides c={c} />
      <p className="small muted">{c.explanation}</p>
      <WhyFlagged c={c} />
      {(can('conflict:review') || can('review:note')) && (
        <div className="row wrap" style={{ marginTop: 14 }}>
          {can('conflict:review') && unresolved && <>
            <Button size="sm" variant="primary" icon={CheckCheck} onClick={() => setOpen('resolve')}>Resolve</Button>
            <Button size="sm" variant="success" icon={BadgeCheck} onClick={() => setOpen('accept')}>Accept Explanation</Button>
            <Button size="sm" icon={Eye} onClick={() => setOpen('mark_reviewed')}>Mark Reviewed</Button>
            {c.status !== 'escalated' && <Button size="sm" variant="danger" icon={TrendingUp} onClick={() => setOpen('escalate')}>Escalate</Button>}
          </>}
          {can('conflict:review') && !unresolved && <Button size="sm" variant="warn" icon={RotateCcw} onClick={() => setOpen('reopen')}>Reopen</Button>}
          <Button size="sm" variant="ghost" icon={MessageSquarePlus} onClick={() => setOpen('note')}>Add Note</Button>
        </div>
      )}
      {open && <ReviewDialog conflict={c} initial={open} onClose={() => setOpen(null)} onDone={onChanged} />}
    </article>
  )
}
