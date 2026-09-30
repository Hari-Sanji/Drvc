import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ChevronDown, FileSearch, FileStack, Fingerprint, ScanLine, Search, ShieldCheck, Trash2, Upload } from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import {
  Button, Confirm, CopyButton, Empty, ErrorState, FileIcon, PageHead, Pagination, Principle, Skeleton, StatusBadge, fmtBytes,
  fmtDateTime, shortHash, useAsync, useDebounced, useToast,
} from '../ui'

export function RecordCards({ records, onDeleted, showCase }) {
  const { can } = useAuth()
  const toast = useToast()
  const [open, setOpen] = useState(null)
  const [del, setDel] = useState(null)
  if (!records.length) return <Empty icon={FileStack} title="No records uploaded">No records uploaded. Add records to begin contextual analysis.</Empty>
  return (
    <div className="stack" style={{ gap: 10 }}>
      {records.map((r, i) => {
        const isOpen = open === r.id
        return (
          <div key={r.id} className="card" style={{ animation: `page-in .4s ${Math.min(i, 12) * 40}ms both` }}>
            <div className="row" style={{ padding: '12px 16px', gap: 14 }}>
              <FileIcon ext={r.ext} />
              <div className="grow">
                <Link to={`/app/records/${r.id}`} style={{ color: 'var(--text)', fontWeight: 600 }} className="truncate">{r.filename}</Link>
                <div className="tiny faint truncate">{r.doc_type} · {fmtBytes(r.size)}{showCase && r.case_code ? <> · <Link to={`/app/cases/${r.case_id}`}>{r.case_code}</Link></> : ''} · uploaded {fmtDateTime(r.uploaded_at)}</div>
              </div>
              <span className="mono tiny hide-sm" style={{ color: 'var(--cyan-2)' }} title={r.sha256 || ''}>{r.sha256 ? shortHash(r.sha256) : '—'}</span>
              <StatusBadge status={r.status} />
              <button className="btn ghost icon sm" aria-expanded={isOpen} aria-label={isOpen ? 'Collapse record' : 'Expand record'} onClick={() => setOpen(isOpen ? null : r.id)}>
                <ChevronDown style={{ transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform .25s' }} />
              </button>
            </div>
            {isOpen && (
              <div style={{ padding: '4px 16px 16px', animation: 'page-in .3s ease both' }}>
                <div className="hash"><Fingerprint size={16} style={{ flex: 'none' }} /><span className="grow">{r.sha256 || 'Not yet generated'}</span>{r.sha256 && <CopyButton text={r.sha256} />}</div>
                <div className="grid g3" style={{ marginTop: 12, gap: 10 }}>
                  <div className="chip" style={{ display: 'block' }}><div className="tiny faint">Text extraction</div><b className="small">{r.text_method}</b>{r.ocr_confidence != null && <div className="tiny" style={{ color: 'var(--cyan-2)' }}>OCR Confidence: {Math.round(r.ocr_confidence)}%</div>}</div>
                  <div className="chip" style={{ display: 'block' }}><div className="tiny faint">Processed</div><b className="small">{fmtDateTime(r.processed_at)}</b></div>
                  <div className="chip" style={{ display: 'block' }}><div className="tiny faint">Pipeline</div><b className="small">{(r.stage_log || []).length} stages logged</b></div>
                </div>
                {r.error && <div className="form-error" style={{ marginTop: 10 }}>{r.error}</div>}
                <div className="row wrap" style={{ marginTop: 12 }}>
                  <Link className="btn sm primary" to={`/app/records/${r.id}`}>Open record details</Link>
                  <Link className="btn sm" to={`/app/records/${r.id}#extracted`}>Extracted information</Link>
                  {can('record:delete') && <Button size="sm" variant="danger" icon={Trash2} onClick={() => setDel(r)}>Delete</Button>}
                </div>
              </div>
            )}
          </div>
        )
      })}
      {del && <Confirm danger title="Delete record?" message={`${del.filename} and its extracted data will be permanently removed; relationships and conflicts are recomputed. The deletion is recorded in the audit log.`}
        confirmLabel="Delete record" onClose={() => setDel(null)}
        onConfirm={async () => { try { await api.del(`/records/${del.id}`); toast('Record deleted', 'success'); onDeleted?.() } catch (e) { toast(e.message, 'error') } setDel(null) }} />}
    </div>
  )
}

function FingerprintCheck() {
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const input = useRef(null)
  const check = async (file) => {
    if (!file) return
    setBusy(true)
    try {
      const fd = new FormData(); fd.append('file', file)
      setRes({ name: file.name, ...(await api.post('/records/verify-file', fd)) })
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  return (
    <div className="card">
      <div className="card-head"><h3><ScanLine />Fingerprint check</h3></div>
      <div className="card-body stack">
        <p className="small muted">Compare a local copy of a file against recorded SHA-256 fingerprints. The file is hashed on the server and <b>not stored</b>.</p>
        <Button icon={Upload} loading={busy} onClick={() => input.current?.click()}>Choose a file to compare</Button>
        <input ref={input} type="file" hidden onChange={(e) => { check(e.target.files[0]); e.target.value = '' }} />
        {res && (
          <div className="stack" style={{ gap: 8 }}>
            <div className="tiny faint">{res.name} · {fmtBytes(res.size)}</div>
            <div className="hash" style={{ fontSize: 11.5 }}>{res.sha256}</div>
            {res.matches.length ? res.matches.map((m) => (
              <Link key={m.id} to={`/app/records/${m.id}`} className="chip" style={{ borderColor: 'rgba(16,185,129,.4)' }}><ShieldCheck size={15} color="var(--green-2)" />Content identical to recorded fingerprint of <b>{m.filename}</b> ({m.case_code})</Link>
            )) : <div className="chip" style={{ borderColor: 'rgba(245,158,11,.4)' }}><FileSearch size={15} color="var(--amber-2)" />No record has this fingerprint — the content differs from every recorded version (or was never uploaded).</div>}
            <p className="tiny faint">A matching fingerprint shows the bytes are unchanged relative to the recorded hash; it does not prove the document's real-world truth.</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default function Records() {
  const [sp] = useSearchParams()
  const [f, setF] = useState({ case_id: sp.get('case') || '', kind: '', status: '', has_conflict: '', q: '' })
  const [page, setPage] = useState(1)
  const dq = useDebounced(f.q)
  const cases = useAsync(() => api.get('/cases?page_size=200'), [])
  const qs = new URLSearchParams({ page, page_size: 15, ...(f.case_id && { case_id: f.case_id }), ...(f.kind && { kind: f.kind }),
    ...(f.status && { status: f.status }), ...(f.has_conflict && { has_conflict: f.has_conflict }), ...(dq && { q: dq }) }).toString()
  const { data, error, loading, reload } = useAsync(() => api.get(`/records?${qs}`), [qs])
  useEffect(() => setPage(1), [f.case_id, f.kind, f.status, f.has_conflict, dq])
  return (
    <>
      <PageHead eyebrow="Evidence inventory" icon={FileStack} title="Records" lead="Every uploaded record with its SHA-256 fingerprint, extraction method and review status." />
      <div className="grid g3">
        <div className="span2 stack">
          <div className="card pad row wrap" style={{ gap: 10 }}>
            <div className="input-icon grow" style={{ minWidth: 200 }}><Search /><input className="input" placeholder="Filename, type, text or hash…" aria-label="Search records" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} /></div>
            <select className="select" style={{ width: 'auto' }} aria-label="Case" value={f.case_id} onChange={(e) => setF({ ...f, case_id: e.target.value })}>
              <option value="">All cases</option>{cases.data?.items.map((c) => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
            </select>
            <select className="select" style={{ width: 'auto' }} aria-label="Record type" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
              <option value="">All types</option><option value="document">Documents</option><option value="image">Images</option>
            </select>
            <select className="select" style={{ width: 'auto' }} aria-label="Status" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
              <option value="">Any status</option><option>Completed</option><option>Requires Review</option><option>Failed</option>
            </select>
            <select className="select" style={{ width: 'auto' }} aria-label="Conflicts" value={f.has_conflict} onChange={(e) => setF({ ...f, has_conflict: e.target.value })}>
              <option value="">Conflicts: any</option><option value="true">With conflicts</option><option value="false">Without conflicts</option>
            </select>
          </div>
          {error ? <ErrorState error={error} onRetry={reload} /> : loading && !data ? <Skeleton h={300} /> : <>
            <RecordCards records={data.items} showCase onDeleted={() => reload(true)} />
            <div className="card"><Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} /></div>
          </>}
        </div>
        <div className="stack"><FingerprintCheck /><Principle>SHA-256 provides a <b>content fingerprint</b> and helps identify changes to file content relative to the recorded hash. It does not prove the real-world truth of a document.</Principle></div>
      </div>
    </>
  )
}
