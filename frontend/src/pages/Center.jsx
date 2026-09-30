import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  AlertOctagon, BookOpenCheck, CalendarClock, CalendarDays, ClipboardCheck, FileText, FolderKanban, Hash, Network, Search, ShieldCheck,
} from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import { BulkBar, ConflictCard, useSelection } from '../components/Conflicts'
import Graph from '../components/Graph'
import { GenerateReport, ReportList } from '../components/Reports'
import Timeline from '../components/Timeline'
import {
  Button, Empty, ErrorState, Loading, PageHead, Pagination, Principle, StatusBadge, timeAgo, useAsync, useDebounced,
} from '../ui'

function useCasePicker() {
  const [sp, setSp] = useSearchParams()
  const cases = useAsync(() => api.get('/cases?page_size=200'), [])
  const items = cases.data?.items || []
  const fallback = items.find((c) => c.is_demo && c.record_count) || items.find((c) => c.record_count) || items[0]
  const selected = sp.get('case') || (fallback ? String(fallback.id) : '')
  const picker = (
    <select className="select" style={{ width: 'auto', minWidth: 260 }} aria-label="Select case" value={selected}
      onChange={(e) => setSp({ case: e.target.value }, { replace: true })}>
      {items.map((c) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
    </select>
  )
  return { selected, picker, loaded: !!cases.data, empty: cases.data && items.length === 0, error: cases.error }
}

const NoCases = () => <div className="card"><Empty icon={FolderKanban} title="No cases yet">No cases yet. Create your first case to begin record analysis.</Empty></div>

export function TimelinePage() {
  const { selected, picker, loaded, empty } = useCasePicker()
  const tl = useAsync(() => (selected ? api.get(`/cases/${selected}/timeline`) : Promise.resolve(null)), [selected])
  return (
    <>
      <PageHead eyebrow="Chronology" icon={CalendarClock} title="Timeline" lead="Dates and events extracted from every record, reconstructed in order. Click an event to open its source record." actions={loaded && !empty && picker} />
      {empty ? <NoCases /> : tl.error ? <ErrorState error={tl.error} onRetry={tl.reload} /> : !tl.data ? <Loading /> : (
        <div className="card pad">
          <div className="row wrap" style={{ gap: 14, marginBottom: 12 }}>
            <span className="row small" style={{ gap: 6 }}><i style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--cyan)', display: 'inline-block' }} />Normal event</span>
            <span className="row small" style={{ gap: 6 }}><i style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--amber)', display: 'inline-block' }} />Requires review</span>
            <span className="row small" style={{ gap: 6 }}><i style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--red)', display: 'inline-block' }} />Conflicting timestamp</span>
          </div>
          <Timeline events={tl.data.events} counts={tl.data.counts} />
        </div>
      )}
    </>
  )
}

export function GraphPage() {
  const { selected, picker, loaded, empty } = useCasePicker()
  const g = useAsync(() => (selected ? api.get(`/cases/${selected}/graph`) : Promise.resolve(null)), [selected])
  return (
    <>
      <PageHead eyebrow="Relationships" icon={Network} title="Relationship Graph"
        lead="Documents, images, people, organisations, places, identifiers and events connected by relationship signals. Click nodes and edges to inspect evidence." actions={loaded && !empty && picker} />
      {empty ? <NoCases /> : g.error ? <ErrorState error={g.error} onRetry={g.reload} /> : !g.data ? <Loading label="Building relationship map…" /> : <Graph data={g.data} />}
      <div style={{ marginTop: 16 }}><Principle>Edges are labelled <b>Likely Related</b>, <b>Possible Match</b> or <b>Relationship Signal</b> — the system never claims certainty.</Principle></div>
    </>
  )
}

export function ConflictCenter() {
  const [f, setF] = useState({ status: 'unresolved', type: '', case_id: '' })
  const [page, setPage] = useState(1)
  const cases = useAsync(() => api.get('/cases?page_size=200'), [])
  const all = useAsync(() => api.get('/conflicts?page_size=200'), [])
  const qs = new URLSearchParams({ page, page_size: 20, ...(f.status && { status: f.status }), ...(f.type && { type: f.type }), ...(f.case_id && { case_id: f.case_id }) }).toString()
  const { data, error, reload } = useAsync(() => api.get(`/conflicts?${qs}`), [qs])
  useEffect(() => setPage(1), [f.status, f.type, f.case_id])
  const items = all.data?.items || []
  const byType = items.reduce((a, c) => ({ ...a, [c.type]: (a[c.type] || 0) + 1 }), {})
  const open = items.filter((c) => ['requires_review', 'escalated'].includes(c.status)).length
  const selection = useSelection()
  const changed = () => { reload(true); all.reload(true); selection.clear() }
  return (
    <>
      <PageHead eyebrow="Potential inconsistencies" icon={AlertOctagon} title="Conflict Center"
        lead="Values that differ between related records. Each item is a signal for human review — never a finding that a document is fake." />
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="card stat"><div className="stat-icon ic-red"><AlertOctagon /></div><div className="stat-value">{items.length}</div><div className="stat-label">Potential inconsistencies</div></div>
        <div className="card stat"><div className="stat-icon ic-amber"><ClipboardCheck /></div><div className="stat-value">{open}</div><div className="stat-label">Requires review / escalated</div></div>
        <div className="card stat"><div className="stat-icon ic-green"><ShieldCheck /></div><div className="stat-value">{items.length - open}</div><div className="stat-label">Reviewed, accepted or resolved</div></div>
        <div className="card pad"><div className="label" style={{ marginBottom: 8 }}>By type</div>{Object.entries(byType).map(([k, v]) => <div key={k} className="row between small"><span className="muted">{k}</span><b>{v}</b></div>)}{!items.length && <span className="small faint">None</span>}</div>
      </div>
      <div className="card pad row wrap" style={{ marginBottom: 16, gap: 10 }}>
        <div className="seg" role="group" aria-label="Status">
          {[['unresolved', 'Open'], ['', 'All'], ['requires_review', 'Requires Review'], ['escalated', 'Escalated'], ['accepted', 'Accepted'], ['resolved', 'Resolved'], ['reviewed', 'Reviewed']].map(([k, l]) => (
            <button key={k} className={f.status === k ? 'active' : ''} aria-pressed={f.status === k} onClick={() => setF({ ...f, status: k })}>{l}</button>
          ))}
        </div>
        <select className="select" style={{ width: 'auto' }} aria-label="Conflict type" value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}>
          <option value="">All types</option>{['Date Mismatch', 'Identity Mismatch', 'Identifier Mismatch', 'Location Mismatch', 'Amount Mismatch'].map((t) => <option key={t}>{t}</option>)}
        </select>
        <select className="select" style={{ width: 'auto' }} aria-label="Case" value={f.case_id} onChange={(e) => setF({ ...f, case_id: e.target.value })}>
          <option value="">All cases</option>{cases.data?.items.map((c) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
        </select>
      </div>
      {error ? <ErrorState error={error} onRetry={reload} /> : !data ? <Loading /> : data.items.length === 0 ? (
        <div className="card"><Empty icon={ShieldCheck} title="No potential inconsistencies detected">{f.status === 'unresolved' ? 'Nothing is waiting for review. ' : ''}No potential inconsistencies detected in the currently analyzed records.</Empty></div>
      ) : (
        <div className="stack" style={{ gap: 14 }}>
          <BulkBar selected={selection.sel} onClear={selection.clear} onDone={changed} />
          {data.items.map((c, i) => <ConflictCard key={c.id} c={c} showCase delay={i * 50} onChanged={changed}
            selected={selection.sel.includes(c.id)} onSelect={selection.toggle} />)}
          <div className="card"><Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} /></div>
        </div>
      )}
    </>
  )
}

export function ReviewCenter() {
  const { can } = useAuth()
  const q = useAsync(() => api.get('/conflicts?status=unresolved&page_size=100'), [])
  const hist = useAsync(() => api.get('/reviews?page_size=40'), [])
  const selection = useSelection()
  const changed = () => { q.reload(true); hist.reload(true); selection.clear() }
  return (
    <>
      <PageHead eyebrow="Human review" icon={ClipboardCheck} title="Review Center"
        lead={can('conflict:review') ? 'Resolve, accept, mark as reviewed or escalate each item. Every decision requires a reason and is written to the audit trail.' : 'Your role can follow review progress' + (can('review:note') ? ' and add notes.' : '.')} />
      <div className="grid g3">
        <div className="span2 stack" style={{ gap: 14 }}>
          <div className="row between wrap"><h2 className="row" style={{ fontSize: 17 }}><ClipboardCheck size={18} color="var(--amber-2)" />Review queue</h2>
            <div className="row">{can('conflict:review') && q.data?.items.length > 1 && <Button size="sm" variant="ghost" onClick={() => selection.setSel(selection.sel.length === q.data.items.length ? [] : q.data.items.map((x) => x.id))}>{selection.sel.length === q.data.items.length ? 'Clear selection' : 'Select all'}</Button>}
            {q.data && <span className="badge b-amber">{q.data.total} open</span>}</div></div>
          <BulkBar selected={selection.sel} onClear={selection.clear} onDone={changed} />
          {q.error ? <ErrorState error={q.error} onRetry={q.reload} /> : !q.data ? <Loading /> : q.data.items.length === 0
            ? <div className="card"><Empty icon={ShieldCheck} title="Review queue is clear">No potential inconsistencies are waiting for review.</Empty></div>
            : q.data.items.map((c, i) => <ConflictCard key={c.id} c={c} showCase delay={i * 50} onChanged={changed}
                selected={selection.sel.includes(c.id)} onSelect={selection.toggle} />)}
        </div>
        <div className="stack">
          <Principle />
          <div className="card">
            <div className="card-head"><h3><ClipboardCheck />Recent review actions</h3></div>
            <div className="card-body stack" style={{ gap: 10, maxHeight: 640, overflowY: 'auto' }}>
              {!hist.data ? <Loading /> : hist.data.items.length === 0 ? <p className="small muted">No review actions yet.</p> : hist.data.items.map((h) => (
                <div key={h.id} className="chip" style={{ display: 'block' }}>
                  <div className="row between"><b className="small">{h.user} <span className="faint" style={{ fontWeight: 500 }}>· {h.role}</span></b><span className="tiny faint">{timeAgo(h.at)}</span></div>
                  <div className="small">{h.action === 'note' ? 'Added a note' : h.action.replace('_', ' ')} · <span className="muted">{h.subject}</span></div>
                  {h.from !== h.to && <div className="tiny faint">{h.from_label} → {h.to_label}</div>}
                  {h.note && <div className="small muted">Reason: {h.note}</div>}
                  {h.case && <Link className="tiny" to={`/app/cases/${h.case.id}/review`}>{h.case.code}</Link>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

export function ReportsPage() {
  const { can } = useAuth()
  const [gen, setGen] = useState(null)
  const [caseId, setCaseId] = useState('')
  const cases = useAsync(() => api.get('/cases?page_size=200'), [])
  const { data, error, reload } = useAsync(() => api.get('/reports?page_size=100'), [])
  useEffect(() => { if (!caseId && cases.data?.items.length) setCaseId(String((cases.data.items.find((c) => c.is_demo) || cases.data.items[0]).id)) }, [cases.data, caseId])
  return (
    <>
      <PageHead eyebrow="Verification reports" icon={BookOpenCheck} title="Reports"
        lead="Downloadable contextual verification reports with hashes, extracted information, timeline, relationships, conflicts, review actions, audit data and limitations."
        actions={can('report:generate') && cases.data?.items.length > 0 && <>
          <select className="select" style={{ width: 'auto' }} aria-label="Case for report" value={caseId} onChange={(e) => setCaseId(e.target.value)}>
            {cases.data.items.map((c) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
          </select>
          <Button variant="primary" icon={BookOpenCheck} onClick={() => setGen(Number(caseId))} disabled={!caseId}>Generate report</Button>
        </>} />
      <div className="card">{error ? <ErrorState error={error} onRetry={reload} /> : !data ? <Loading /> : <ReportList reports={data.items} showCase />}</div>
      <div style={{ marginTop: 16 }}><Principle>Every report carries the disclaimer: it presents extracted digital evidence signals and <b>does not establish absolute authenticity</b> or prove a real-world event.</Principle></div>
      {gen && <GenerateReport caseId={gen} onClose={() => setGen(null)} onDone={() => reload(true)} />}
    </>
  )
}

export function SearchPage() {
  const [sp, setSp] = useSearchParams()
  const [f, setF] = useState({ q: sp.get('q') || '', case_id: '', kind: '', status: '', date_from: '', date_to: '', conflict: '', review: '' })
  const dq = useDebounced(f.q, 350)
  const cases = useAsync(() => api.get('/cases?page_size=200'), [])
  useEffect(() => { const q = sp.get('q') || ''; setF((x) => (x.q === q ? x : { ...x, q })) }, [sp])
  const qs = new URLSearchParams(Object.fromEntries(Object.entries({ ...f, q: dq, limit: 25 }).filter(([, v]) => v !== ''))).toString()
  const { data, error } = useAsync(() => api.get(`/search?${qs}`), [qs])
  const total = data ? data.cases.length + data.records.length + data.entities.length + data.events.length + data.conflicts.length : 0
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  return (
    <>
      <PageHead eyebrow="Global search" icon={Search} title="Search" lead="Search across cases, records, names, IDs, locations, organisations, events and conflicts." />
      <div className="card pad stack" style={{ marginBottom: 16 }}>
        <div className="input-icon"><Search /><input className="input" autoFocus placeholder="e.g. Rahul, WGU22CS045, Coimbatore, invoice…" aria-label="Search query" value={f.q}
          onChange={(e) => { setF({ ...f, q: e.target.value }); setSp(e.target.value ? { q: e.target.value } : {}, { replace: true }) }} /></div>
        <div className="row wrap" style={{ gap: 10 }}>
          <select className="select" style={{ width: 'auto' }} aria-label="Case" value={f.case_id} onChange={set('case_id')}><option value="">All cases</option>{cases.data?.items.map((c) => <option key={c.id} value={c.id}>{c.code}</option>)}</select>
          <select className="select" style={{ width: 'auto' }} aria-label="Record type" value={f.kind} onChange={set('kind')}><option value="">Any record type</option><option value="document">Documents</option><option value="image">Images</option>{['pdf', 'docx', 'txt', 'png', 'jpg'].map((x) => <option key={x} value={x}>{x.toUpperCase()}</option>)}</select>
          <select className="select" style={{ width: 'auto' }} aria-label="Status" value={f.status} onChange={set('status')}><option value="">Any status</option><option>Completed</option><option>Requires Review</option><option value="active">Case: Active</option><option value="requires_review">Case: Requires Review</option><option value="completed">Case: Completed</option></select>
          <select className="select" style={{ width: 'auto' }} aria-label="Conflict" value={f.conflict} onChange={set('conflict')}><option value="">Conflict: any</option><option value="yes">Has conflict</option><option value="no">No conflict</option></select>
          <select className="select" style={{ width: 'auto' }} aria-label="Review status" value={f.review} onChange={set('review')}><option value="">Review: any</option><option value="open">Open</option><option value="done">Reviewed</option></select>
          <label className="row small muted" style={{ gap: 6 }}>From<input type="date" className="input" style={{ width: 'auto' }} value={f.date_from} onChange={set('date_from')} /></label>
          <label className="row small muted" style={{ gap: 6 }}>To<input type="date" className="input" style={{ width: 'auto' }} value={f.date_to} onChange={set('date_to')} /></label>
        </div>
      </div>
      {error ? <ErrorState error={error} /> : !data ? <Loading label="Searching…" /> : total === 0 ? (
        <div className="card"><Empty icon={Search} title={f.q.length < 2 && !qs.includes('=') ? 'Start typing to search' : 'No results'}>Try a name, identifier, place, organisation or date.</Empty></div>
      ) : (
        <div className="grid g2">
          {data.cases.length > 0 && <ResultCard icon={FolderKanban} title="Cases">{data.cases.map((c) => <Link key={c.id} className="sr-item" to={`/app/cases/${c.id}`}><FolderKanban /><span className="grow">{c.name}</span><StatusBadge kind="case" status={c.status} /></Link>)}</ResultCard>}
          {data.records.length > 0 && <ResultCard icon={FileText} title="Records">{data.records.map((r) => <Link key={r.id} className="sr-item" to={`/app/records/${r.id}`}><FileText /><span className="grow" style={{ minWidth: 0 }}><span className="truncate" style={{ display: 'block' }}>{r.filename}</span>{r.snippet && <span className="tiny faint truncate" style={{ display: 'block' }}>…{r.snippet}…</span>}</span><StatusBadge status={r.status} /></Link>)}</ResultCard>}
          {data.entities.length > 0 && <ResultCard icon={Hash} title="Names, IDs, places & organisations">{data.entities.map((e, i) => <Link key={i} className="sr-item" to={`/app/records/${e.record_ids[0]}#extracted`}><Hash /><span className="grow">{e.value}</span><span className={`badge e-${e.type}`} style={{ border: '1px solid' }}>{e.type}</span><span className="tiny faint">{e.record_ids.length} rec.</span></Link>)}</ResultCard>}
          {data.events.length > 0 && <ResultCard icon={CalendarDays} title="Events">{data.events.map((e) => <Link key={e.id} className="sr-item" to={`/app/records/${e.record_id}#events`}><CalendarDays /><span className="grow">{e.label}</span><span className="tiny faint">{e.date_label}</span></Link>)}</ResultCard>}
          {data.conflicts.length > 0 && <ResultCard icon={AlertOctagon} title="Conflicts">{data.conflicts.map((c) => <Link key={c.id} className="sr-item" to={`/app/cases/${c.case_id}/conflicts`}><AlertOctagon /><span className="grow">{c.type} · {c.field}</span><StatusBadge kind="conflict" status={c.status} /></Link>)}</ResultCard>}
        </div>
      )}
    </>
  )
}

const ResultCard = ({ icon: I, title, children }) => (
  <div className="card"><div className="card-head"><h3><I />{title}</h3></div><div className="sr-group">{children}</div></div>
)
