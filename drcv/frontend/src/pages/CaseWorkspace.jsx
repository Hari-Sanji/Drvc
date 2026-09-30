import { useCallback, useEffect, useState } from 'react'
import { Link, NavLink, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  AlertOctagon, BookOpenCheck, CalendarClock, CalendarRange, ClipboardCheck, FileStack, Fingerprint, FolderKanban, LayoutGrid, Link2,
  MessageSquarePlus, Network, Pencil, Play, ScrollText, ShieldCheck, Tags, User, Users,
} from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import { BulkBar, ConflictCard, UNRESOLVED, useSelection } from '../components/Conflicts'
import Graph from '../components/Graph'
import PipelineOverlay from '../components/Pipeline'
import { GenerateReport, ReportList } from '../components/Reports'
import Timeline from '../components/Timeline'
import UploadZone from '../components/Upload'
import {
  Button, Counter, Empty, ErrorState, Loading, Principle, StatusBadge, Synthetic, fmtDate, fmtDateTime, fmtIsoDate, timeAgo, useAsync, useInterval, useToast,
} from '../ui'
import { AuditTable } from './Audit'
import { CaseForm } from './Cases'
import { RecordCards } from './Records'

const TABS = [
  ['overview', 'Overview', LayoutGrid], ['records', 'Records', FileStack], ['timeline', 'Timeline', CalendarClock],
  ['relationships', 'Relationships', Network], ['conflicts', 'Conflicts', AlertOctagon], ['review', 'Review', ClipboardCheck],
  ['reports', 'Reports', BookOpenCheck], ['audit', 'Audit', ScrollText],
]

export default function CaseWorkspace() {
  const { id, tab = 'overview' } = useParams()
  const [sp, setSp] = useSearchParams()
  const { can } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const [version, setVersion] = useState(0)
  const [edit, setEdit] = useState(false)
  const [pipeline, setPipeline] = useState(sp.get('pipeline') === '1')
  const ov = useAsync(() => api.get(`/cases/${id}/overview`), [id, version])
  const processing = ov.data?.records.some((r) => !['Completed', 'Requires Review', 'Failed'].includes(r.status))
  useInterval(() => ov.reload(true), 2500, !!processing)
  useEffect(() => { if (sp.get('pipeline') === '1') { setPipeline(true); sp.delete('pipeline'); setSp(sp, { replace: true }) } }, [sp, setSp])
  const refresh = useCallback(() => setVersion((v) => v + 1), [])

  const runAnalysis = async () => {
    try { await api.post(`/cases/${id}/analyze`); setPipeline(true) } catch (e) { toast(e.message, 'error') }
  }
  if (ov.error) return <ErrorState error={ov.error} onRetry={ov.reload} />
  if (!ov.data) return <Loading label="Opening case workspace…" />
  const { case: c, stats } = ov.data
  return (
    <>
      <div className="card pad glow-border" style={{ marginBottom: 16 }}>
        <div className="row wrap between" style={{ gap: 16 }}>
          <div style={{ minWidth: 0 }}>
            <div className="row wrap" style={{ gap: 10, marginBottom: 8 }}>
              <Link to="/app/cases" className="row small muted" style={{ gap: 5 }}><FolderKanban size={14} />Cases</Link>
              <span className="faint">/</span><span className="mono small" style={{ color: 'var(--violet-2)' }}>{c.code}</span>
              <StatusBadge kind="case" status={c.status} />{c.is_demo && <Synthetic />}
            </div>
            <h1>{c.name}</h1>
            <div className="row wrap small muted" style={{ marginTop: 8, gap: 16 }}>
              <span className="row" style={{ gap: 5 }}><CalendarRange size={14} />Created {fmtDate(c.created_at)}</span>
              <span className="row" style={{ gap: 5 }}><User size={14} />Owner: {c.owner?.name || '—'}</span>
              <span className="row" style={{ gap: 5 }}><Tags size={14} />{c.category}</span>
              {c.assignees.length > 0 && <span className="row" style={{ gap: 5 }}><Users size={14} />Reviewer: {c.assignees.map((a) => a.name).join(', ')}</span>}
            </div>
          </div>
          <div className="row wrap">
            {can('case:update') && <Button icon={Pencil} onClick={() => setEdit(true)}>Edit</Button>}
            {can('analysis:run') && <Button variant="primary" icon={Play} onClick={runAnalysis} disabled={!stats.records}>Run analysis</Button>}
          </div>
        </div>
      </div>
      <nav className="tabs" aria-label="Case sections" style={{ marginBottom: 18 }}>
        {TABS.map(([k, l, I]) => (
          <NavLink key={k} to={`/app/cases/${id}/${k}`} className={() => (tab === k ? 'active' : '')} end>
            <I aria-hidden />{l}{k === 'conflicts' && stats.unresolved > 0 && <span className="count">{stats.unresolved}</span>}
          </NavLink>
        ))}
      </nav>
      <div key={`${tab}-${version}`} style={{ animation: 'page-in .4s ease both' }}>
        {tab === 'overview' && <Overview data={ov.data} onTab={(t) => navigate(`/app/cases/${id}/${t}`)} />}
        {tab === 'records' && <RecordsTab data={ov.data} onChange={() => ov.reload(true)} refresh={refresh} />}
        {tab === 'timeline' && <TimelineTab id={id} />}
        {tab === 'relationships' && <GraphTab id={id} />}
        {tab === 'conflicts' && <ConflictsTab id={id} onChange={() => ov.reload(true)} />}
        {tab === 'review' && <ReviewTab id={id} onChange={() => ov.reload(true)} />}
        {tab === 'reports' && <ReportsTab id={id} hasRecords={stats.records > 0} />}
        {tab === 'audit' && (can('audit:view') ? <AuditTable caseId={id} compact /> : <div className="card"><Empty icon={ScrollText} title="Audit log not available for your role">Viewers have read-only access to cases, records, timelines, relationships and reports.</Empty></div>)}
      </div>
      {edit && <CaseForm initial={c} onClose={() => setEdit(false)} onSaved={() => ov.reload(true)} />}
      {pipeline && <PipelineOverlay caseId={id} onClose={() => { setPipeline(false); refresh() }} onComplete={refresh} />}
    </>
  )
}

function Overview({ data, onTab }) {
  const { case: c, stats } = data
  const tiles = [
    ['Records', stats.records, FileStack, 'ic-violet', 'records'], ['SHA-256 fingerprints', stats.hashed, Fingerprint, 'ic-cyan', 'records'],
    ['Relationship signals', stats.relationships, Link2, 'ic-blue', 'relationships'], ['Timeline events', stats.events, CalendarClock, 'ic-amber', 'timeline'],
    ['Potential inconsistencies', stats.conflicts, AlertOctagon, 'ic-red', 'conflicts'], ['Awaiting review', stats.unresolved, ClipboardCheck, 'ic-amber', 'review'],
  ]
  const as = c.analysis_state || {}
  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="grid g3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
        {tiles.map(([l, v, I, ic, t], i) => (
          <button key={l} className="card stat hover" onClick={() => onTab(t)} style={{ textAlign: 'left', color: 'inherit', cursor: 'pointer', animation: `page-in .45s ${i * 60}ms both` }}>
            <div className={`stat-icon ${ic}`}><I /></div><div className="stat-value"><Counter value={v} /></div><div className="stat-label">{l}</div>
          </button>
        ))}
      </div>
      <div className="grid g3">
        <div className="card span2">
          <div className="card-head"><h3><FolderKanban />About this case</h3>{as.finished_at && <span className="tiny faint">Last full analysis {timeAgo(as.finished_at)}</span>}</div>
          <div className="card-body stack">
            <p className="muted">{c.description || 'No description provided.'}</p>
            <div className="kv">
              <div>Case ID</div><div className="mono">{c.code}</div>
              <div>Review status</div><div>{c.review_status}</div>
              <div>Date span of events</div><div>{data.date_span ? `${fmtIsoDate(data.date_span[0])} → ${fmtIsoDate(data.date_span[1])}` : '—'}</div>
              <div>Records with OCR</div><div>{stats.ocr_records}</div>
              <div>Entities extracted</div><div>{stats.entities} {Object.entries(data.entity_counts).map(([k, v]) => <span key={k} className={`badge e-${k}`} style={{ marginLeft: 6, border: '1px solid' }}>{k} {v}</span>)}</div>
              <div>Last updated</div><div>{fmtDateTime(c.updated_at)}</div>
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-head"><h3><AlertOctagon />Inconsistency types</h3></div>
          <div className="card-body stack" style={{ gap: 10 }}>
            {Object.keys(data.conflict_types).length === 0 ? <p className="small muted">No potential inconsistencies detected in the currently analyzed records.</p> :
              Object.entries(data.conflict_types).map(([k, v]) => <div key={k} className="row between"><span className="small">{k}</span><span className="badge b-red">{v}</span></div>)}
            <Button size="sm" onClick={() => onTab('conflicts')}>Open conflicts</Button>
          </div>
        </div>
      </div>
      <div className="card">
        <div className="card-head"><h3><FileStack />Records in this case</h3><Button size="sm" onClick={() => onTab('records')}>Manage records</Button></div>
        <div className="card-body">
          {data.records.length === 0 ? <Empty icon={FileStack} title="No records uploaded">No records uploaded. Add records to begin contextual analysis.</Empty> : (
            <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))', gap: 10 }}>
              {data.records.map((r) => (
                <Link key={r.id} to={`/app/records/${r.id}`} className="chip" style={{ color: 'var(--text)', textDecoration: 'none', padding: 12, display: 'block' }}>
                  <div className="row between"><b className="small truncate">{r.doc_type}</b><StatusBadge status={r.status} /></div>
                  <div className="tiny faint truncate" style={{ marginTop: 4 }}>{r.filename}</div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
      <Principle />
    </div>
  )
}

function RecordsTab({ data, onChange }) {
  const { can } = useAuth()
  const settings = useAsync(() => api.get('/settings'), [])
  return (
    <div className="stack" style={{ gap: 16 }}>
      {can('record:upload') && !data.case.archived && <UploadZone caseId={data.case.id} maxMb={settings.data?.settings.max_upload_mb || 20} onUploaded={onChange} onRecordDone={onChange} />}
      <RecordCards records={[...data.records].reverse()} onDeleted={onChange} />
    </div>
  )
}

function TimelineTab({ id }) {
  const { data, error, reload } = useAsync(() => api.get(`/cases/${id}/timeline`), [id])
  if (error) return <ErrorState error={error} onRetry={reload} />
  if (!data) return <Loading />
  return <div className="card pad"><Timeline events={data.events} counts={data.counts} /></div>
}

function GraphTab({ id }) {
  const g = useAsync(() => api.get(`/cases/${id}/graph`), [id])
  const rels = useAsync(() => api.get(`/cases/${id}/relationships`), [id])
  if (g.error) return <ErrorState error={g.error} onRetry={g.reload} />
  if (!g.data) return <Loading label="Building relationship map…" />
  return (
    <div className="stack" style={{ gap: 16 }}>
      <Graph data={g.data} />
      {rels.data?.length > 0 && (
        <div className="card">
          <div className="card-head"><h3><Link2 />Record-to-record relationship signals</h3><span className="tiny faint">Language reflects uncertainty — never certainty</span></div>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Records</th><th>Signal</th><th>Strength</th><th className="hide-sm">Evidence</th></tr></thead>
            <tbody>{rels.data.map((r) => (
              <tr key={r.id}>
                <td className="small"><Link to={`/app/records/${r.source.id}`}>{r.source.doc_type}</Link> ↔ <Link to={`/app/records/${r.target.id}`}>{r.target.doc_type}</Link></td>
                <td><span className={`badge ${r.score >= 0.75 ? 'b-cyan' : r.score >= 0.45 ? 'b-violet' : 'b-neutral'}`}>{r.label}</span><div className="tiny faint" style={{ marginTop: 4 }}>{r.type}</div></td>
                <td><div className="row small" style={{ gap: 8 }}><div className="conf-bar" style={{ width: 80 }}><span style={{ width: `${r.score * 100}%` }} /></div>{Math.round(r.score * 100)}%</div></td>
                <td className="tiny muted hide-sm">{r.evidence.slice(0, 3).map((e) => `${e.type}: ${e.value}`).join(' · ')}</td>
              </tr>))}</tbody>
          </table></div>
        </div>
      )}
    </div>
  )
}

function ConflictsTab({ id, onChange }) {
  const { data, error, reload } = useAsync(() => api.get(`/conflicts?case_id=${id}&page_size=100`), [id])
  const selection = useSelection()
  if (error) return <ErrorState error={error} onRetry={reload} />
  if (!data) return <Loading />
  if (!data.items.length) return <div className="card"><Empty icon={ShieldCheck} title="No potential inconsistencies detected">No potential inconsistencies detected in the currently analyzed records.</Empty></div>
  return (
    <div className="stack" style={{ gap: 14 }}>
      <Principle>Each card is a <b>potential inconsistency</b> between extracted values — not a finding of fraud. A reviewer decides what it means.</Principle>
      <BulkBar selected={selection.sel} onClear={selection.clear} onDone={() => { reload(true); onChange(); selection.clear() }} />
      {data.items.map((c, i) => <ConflictCard key={c.id} c={c} delay={i * 60} onChanged={() => { reload(true); onChange() }}
        selected={selection.sel.includes(c.id)} onSelect={selection.toggle} />)}
    </div>
  )
}

function ReviewTab({ id, onChange }) {
  const { can } = useAuth()
  const toast = useToast()
  const confs = useAsync(() => api.get(`/conflicts?case_id=${id}&status=unresolved&page_size=100`), [id])
  const hist = useAsync(() => api.get(`/reviews?case_id=${id}&page_size=50`), [id])
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const selection = useSelection()
  const changed = () => { confs.reload(true); hist.reload(true); onChange(); selection.clear() }
  const addNote = async () => {
    if (note.trim().length < 3) { toast('Please write at least 3 characters.', 'warn'); return }
    setBusy(true)
    try { await api.post(`/cases/${id}/notes`, { note }); setNote(''); toast('Review note added', 'success'); hist.reload(true) } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  return (
    <div className="grid g3">
      <div className="span2 stack" style={{ gap: 14 }}>
        <h2 className="row" style={{ fontSize: 17 }}><ClipboardCheck size={18} color="var(--amber-2)" />Review queue</h2>
        {!confs.data ? <Loading /> : confs.data.items.length === 0 ? <div className="card"><Empty icon={ShieldCheck} title="Review queue is clear">No unresolved items in this case.</Empty></div>
          : <><BulkBar selected={selection.sel} onClear={selection.clear} onDone={changed} />
            {confs.data.items.map((c, i) => <ConflictCard key={c.id} c={c} delay={i * 50} onChanged={changed}
              selected={selection.sel.includes(c.id)} onSelect={selection.toggle} />)}</>}
      </div>
      <div className="stack" style={{ gap: 14 }}>
        {can('review:note') && (
          <div className="card">
            <div className="card-head"><h3><MessageSquarePlus />Add case note</h3></div>
            <div className="card-body stack">
              <textarea className="textarea" aria-label="Case note" value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Requested certified copies from the registrar." />
              <Button variant="primary" loading={busy} onClick={addNote}>Add note</Button>
            </div>
          </div>
        )}
        <div className="card">
          <div className="card-head"><h3><ScrollText />Review history</h3></div>
          <div className="card-body stack" style={{ gap: 10, maxHeight: 560, overflowY: 'auto' }}>
            {!hist.data ? <Loading /> : hist.data.items.length === 0 ? <p className="small muted">No review actions yet.</p> : hist.data.items.map((h) => (
              <div key={h.id} className="chip" style={{ display: 'block' }}>
                <div className="row between"><b className="small">{h.user}</b><span className="tiny faint">{timeAgo(h.at)}</span></div>
                <div className="small">{h.action === 'note' ? 'Added a note' : h.action.replace('_', ' ')} <span className="faint">· {h.subject}</span></div>
                {h.from !== h.to && <div className="tiny faint">{h.from_label} → {h.to_label}</div>}
                {h.note && <div className="small muted">“{h.note}”</div>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function ReportsTab({ id, hasRecords }) {
  const { can } = useAuth()
  const [gen, setGen] = useState(false)
  const { data, error, reload } = useAsync(() => api.get(`/reports?case_id=${id}`), [id])
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="card pad row wrap between">
        <div><h3>Contextual verification report</h3><p className="small muted">Case details, records, SHA-256 hashes, metadata, entities, timeline, relationships, conflicts, review actions, audit and limitations.</p></div>
        {can('report:generate') ? <Button variant="primary" icon={BookOpenCheck} disabled={!hasRecords} onClick={() => setGen(true)}>Generate report</Button> : <span className="badge b-neutral">View & download only</span>}
      </div>
      <div className="card">{error ? <ErrorState error={error} onRetry={reload} /> : !data ? <Loading /> : <ReportList reports={data.items} />}</div>
      {gen && <GenerateReport caseId={Number(id)} onClose={() => setGen(false)} onDone={() => reload(true)} />}
    </div>
  )
}

export { UNRESOLVED }
