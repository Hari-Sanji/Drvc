import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, Link2, Lock, ScrollText, Search, ShieldAlert, ShieldCheck } from 'lucide-react'
import { api, downloadFile } from '../api'
import { useAuth } from '../auth'
import { Button, Empty, ErrorState, PageHead, Pagination, Skeleton, fmtDateTime, useAsync, useDebounced } from '../ui'

const RESULT = { success: 'b-green', denied: 'b-red', failed: 'b-amber' }
const CATS = ['auth', 'case', 'upload', 'pipeline', 'analysis', 'conflict', 'review', 'report', 'integrity', 'record', 'security', 'users', 'settings', 'audit']

export function AuditTable({ caseId, compact }) {
  const [f, setF] = useState({ category: '', result: '', q: '' })
  const [page, setPage] = useState(1)
  const dq = useDebounced(f.q)
  const qs = new URLSearchParams({ page, page_size: compact ? 12 : 25, ...(caseId && { case_id: caseId }), ...(f.category && { category: f.category }),
    ...(f.result && { result: f.result }), ...(dq && { q: dq }) }).toString()
  const { data, error, loading, reload } = useAsync(() => api.get(`/audit?${qs}`), [qs])
  useEffect(() => setPage(1), [f.category, f.result, dq])
  return (
    <div className="card">
      <div className="row wrap" style={{ padding: 14, gap: 10, borderBottom: '1px solid var(--border)' }}>
        <div className="input-icon grow" style={{ minWidth: 200 }}><Search /><input className="input" placeholder="Search actions, users, details…" aria-label="Search audit log" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} /></div>
        <select className="select" style={{ width: 'auto' }} aria-label="Category" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
          <option value="">All categories</option>{CATS.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select className="select" style={{ width: 'auto' }} aria-label="Result" value={f.result} onChange={(e) => setF({ ...f, result: e.target.value })}>
          <option value="">Any result</option><option value="success">Success</option><option value="denied">Denied</option><option value="failed">Failed</option>
        </select>
        <span className="badge b-neutral"><Lock />Read-only</span>
      </div>
      {error ? <ErrorState error={error} onRetry={reload} /> : loading && !data ? <div style={{ padding: 16 }}><Skeleton h={260} /></div> : data.items.length === 0 ? <Empty icon={ScrollText} title="No audit entries match" /> : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Timestamp</th><th>User</th><th>Action</th><th className="hide-sm">Record / case</th><th>Result</th><th className="hide-sm">Chain hash</th></tr></thead>
            <tbody>
              {data.items.map((a) => (
                <tr key={a.id}>
                  <td className="mono tiny" style={{ whiteSpace: 'nowrap' }}>{fmtDateTime(a.ts)}</td>
                  <td className="small"><b>{a.user}</b><div className="tiny faint">{a.role}</div></td>
                  <td className="small" style={{ maxWidth: 440 }}><div style={{ fontWeight: 600 }}>{a.action}</div>{a.details && <div className="tiny faint" style={{ wordBreak: 'break-word' }}>{a.details.length > 180 ? a.details.slice(0, 180) + '…' : a.details}</div>}</td>
                  <td className="small hide-sm">{a.record_id ? <Link to={`/app/records/${a.record_id}`}>{a.target}</Link> : a.case_id ? <Link to={`/app/cases/${a.case_id}`}>{a.target || `Case #${a.case_id}`}</Link> : <span className="faint">{a.target || '—'}</span>}</td>
                  <td><span className={`badge ${RESULT[a.result] || 'b-neutral'}`}>{a.result}</span></td>
                  <td className="mono tiny hide-sm" style={{ color: 'var(--cyan-2)' }} title={a.hash || ''}>{a.hash ? `${a.hash.slice(0, 10)}…` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />}
    </div>
  )
}

function ChainCheck() {
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true)
    try { setRes(await api.get('/audit/verify')) } catch (e) { setRes({ ok: false, message: e.message }) } finally { setBusy(false) }
  }
  return (
    <div className="card pad row wrap between" style={{ marginBottom: 16, gap: 14 }}>
      <div className="row" style={{ gap: 12, minWidth: 0 }}>
        <div className={`stat-icon ${res ? (res.ok ? 'ic-green' : 'ic-red') : 'ic-violet'}`} style={{ width: 40, height: 40, borderRadius: 12, display: 'grid', placeItems: 'center', flex: 'none' }}>
          {res && !res.ok ? <ShieldAlert size={19} /> : <Link2 size={19} />}
        </div>
        <div style={{ minWidth: 0 }}>
          <b>Tamper-evident log</b>
          <div className={`small ${res ? (res.ok ? 'chain-ok' : 'chain-bad') : 'muted'}`}>
            {res ? res.message : 'Each entry stores the SHA-256 of the previous one. Editing or deleting any past entry breaks the chain.'}
          </div>
          {res?.head && <div className="tiny faint mono" style={{ wordBreak: 'break-all' }}>Chain head: {res.head}</div>}
        </div>
      </div>
      <Button icon={res?.ok ? ShieldCheck : Link2} loading={busy} onClick={run}>{res ? 'Verify again' : 'Verify integrity'}</Button>
    </div>
  )
}

export default function Audit() {
  const { can } = useAuth()
  return (
    <>
      <PageHead eyebrow="Governance" icon={ScrollText} title="Audit Logs"
        lead="An append-only, hash-chained trail of every user and system action — uploads, hashing, OCR, detections, review decisions, reports and denied access attempts."
        actions={can('audit:export') && <Button icon={Download} onClick={() => downloadFile('/audit/export', 'drcv-audit-log.csv')}>Export CSV</Button>} />
      <ChainCheck />
      <AuditTable />
    </>
  )
}
