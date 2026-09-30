import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Archive, ArchiveRestore, FileStack, FolderKanban, FolderPlus, Pencil, Search, ShieldAlert, Trash2, User } from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import {
  Button, Confirm, Empty, ErrorState, Modal, PageHead, Pagination, SkeletonCards, StatusBadge, Synthetic, fmtDate, useAsync, useDebounced, useToast,
} from '../ui'

export function CaseForm({ initial, onClose, onSaved }) {
  const { can } = useAuth()
  const toast = useToast()
  const [f, setF] = useState({ name: initial?.name || '', description: initial?.description || '', category: initial?.category || 'General',
    status: initial ? (initial.status_locked ? initial.status : 'auto') : 'auto' })
  const [reviewers, setReviewers] = useState(null)
  const [assigned, setAssigned] = useState(new Set(initial?.assignees?.map((a) => a.id) || []))
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (initial && can('case:assign')) api.get('/users/reviewers').then(setReviewers).catch(() => setReviewers([])) }, [initial, can])

  const save = async () => {
    if (f.name.trim().length < 3) { setErr('Case name must be at least 3 characters.'); return }
    setBusy(true); setErr('')
    try {
      let c
      if (initial) {
        c = await api.patch(`/cases/${initial.id}`, { name: f.name, description: f.description, category: f.category, ...(f.status !== (initial.status_locked ? initial.status : 'auto') ? { status: f.status } : {}) })
        if (reviewers) c = await api.put(`/cases/${initial.id}/assignments`, { user_ids: [...assigned] })
      } else {
        c = await api.post('/cases', { name: f.name, description: f.description, category: f.category })
      }
      toast(initial ? 'Case updated' : `Case ${c.code} created`, 'success')
      onSaved?.(c)
      onClose()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <Modal title={initial ? `Edit ${initial.code}` : 'Create case'} icon={initial ? Pencil : FolderPlus} onClose={onClose}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>{initial ? 'Save changes' : 'Create case'}</Button></>}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save() }}>
        <div className="field"><label htmlFor="cn">Case name</label><input id="cn" className="input" maxLength={200} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="e.g. Employment Record Verification" /></div>
        <div className="field"><label htmlFor="cc">Category</label>
          <select id="cc" className="select" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
            {['General', 'Academic Records', 'Financial Records', 'Identity Records', 'Property Records', 'Employment Records', 'Legal Records', 'Incident Investigation'].map((x) => <option key={x}>{x}</option>)}
          </select></div>
        <div className="field"><label htmlFor="cd">Description</label><textarea id="cd" className="textarea" maxLength={4000} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="What is being verified, and why?" /></div>
        {initial && (
          <div className="field"><label htmlFor="cs">Status</label>
            <select id="cs" className="select" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>
              <option value="auto">Automatic (derived from analysis)</option>
              <option value="active">Active</option><option value="processing">Processing</option>
              <option value="requires_review">Requires Review</option><option value="completed">Completed</option>
            </select></div>
        )}
        {reviewers && (
          <div className="field"><span className="label">Assigned reviewers</span>
            {reviewers.length === 0 ? <span className="small faint">No reviewer accounts exist.</span> : reviewers.map((r) => (
              <label key={r.id} className="checkbox"><input type="checkbox" checked={assigned.has(r.id)} onChange={(e) => { const n = new Set(assigned); e.target.checked ? n.add(r.id) : n.delete(r.id); setAssigned(n) }} />{r.name} <span className="faint">({r.email})</span></label>
            ))}
            <span className="tiny faint">Reviewers only see cases assigned to them.</span>
          </div>
        )}
        {err && <div className="form-error" role="alert">{err}</div>}
      </form>
    </Modal>
  )
}

export default function Cases() {
  const { can } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const dq = useDebounced(q)
  const [modal, setModal] = useState(null)
  const { data, error, loading, reload } = useAsync(() => api.get(`/cases?page=${page}&page_size=12${status ? `&status=${status}` : ''}${dq ? `&q=${encodeURIComponent(dq)}` : ''}`), [status, dq, page])
  useEffect(() => setPage(1), [status, dq])

  const act = async (fn, msg) => { try { await fn(); toast(msg, 'success'); reload(true) } catch (e) { toast(e.message, 'error') } }
  return (
    <>
      <PageHead eyebrow="Case management" icon={FolderKanban} title="Cases"
        lead="Each case groups the records produced by one real-world incident or verification task."
        actions={can('case:create') && <Button variant="primary" icon={FolderPlus} onClick={() => setModal({ type: 'new' })}>Create case</Button>} />
      <div className="row wrap between" style={{ marginBottom: 16 }}>
        <div className="seg" role="group" aria-label="Filter by status">
          {[['', 'All'], ['active', 'Active'], ['processing', 'Processing'], ['requires_review', 'Requires Review'], ['completed', 'Completed'], ['archived', 'Archived']].map(([k, l]) => (
            <button key={k} className={status === k ? 'active' : ''} aria-pressed={status === k} onClick={() => setStatus(k)}>{l}</button>
          ))}
        </div>
        <div className="input-icon" style={{ width: 300, maxWidth: '100%' }}><Search /><input className="input" placeholder="Search cases…" aria-label="Search cases" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>
      {error ? <ErrorState error={error} onRetry={reload} /> : loading && !data ? <SkeletonCards n={6} h={190} /> : data.items.length === 0 ? (
        <div className="card"><Empty icon={FolderKanban} title={q || status ? 'No matching cases' : 'No cases yet'}
          action={can('case:create') && !q && !status && <Button variant="primary" icon={FolderPlus} onClick={() => setModal({ type: 'new' })}>Create case</Button>}>
          {q || status ? 'Try a different filter or search term.' : 'No cases yet. Create your first case to begin record analysis.'}</Empty></div>
      ) : (
        <>
          <div className="grid g3">
            {data.items.map((c, i) => (
              <article key={c.id} className="card pad hover" style={{ cursor: 'pointer', animation: `page-in .45s ${i * 50}ms both` }}
                onClick={() => navigate(`/app/cases/${c.id}`)} tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && navigate(`/app/cases/${c.id}`)} aria-label={`Open case ${c.name}`}>
                <div className="row between"><span className="mono tiny faint">{c.code}</span><StatusBadge kind="case" status={c.status} /></div>
                <h3 style={{ fontSize: 17, marginTop: 10 }}>{c.name}</h3>
                <p className="small muted" style={{ marginTop: 6, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', minHeight: 40 }}>{c.description || 'No description.'}</p>
                <div className="row wrap" style={{ marginTop: 14, gap: 14 }}>
                  <span className="row small muted" style={{ gap: 5 }}><FileStack size={14} />{c.record_count} records</span>
                  <span className="row small" style={{ gap: 5, color: c.unresolved_count ? 'var(--red-2)' : 'var(--text-2)' }}><ShieldAlert size={14} />{c.conflict_count} conflicts</span>
                  <span className="row small muted" style={{ gap: 5 }}><User size={14} />{c.owner?.name || '—'}</span>
                </div>
                <div className="divider" />
                <div className="row between">
                  <span className="tiny faint">{c.review_status} · created {fmtDate(c.created_at)}</span>
                  <div className="row" style={{ gap: 2 }} onClick={(e) => e.stopPropagation()}>
                    {can('case:update') && <button className="btn ghost icon sm" aria-label="Edit case" data-tip="Edit" onClick={() => setModal({ type: 'edit', c })}><Pencil /></button>}
                    {can('case:archive') && (c.archived
                      ? <button className="btn ghost icon sm" aria-label="Restore case" data-tip="Restore" onClick={() => act(() => api.post(`/cases/${c.id}/unarchive`), 'Case restored')}><ArchiveRestore /></button>
                      : <button className="btn ghost icon sm" aria-label="Archive case" data-tip="Archive" onClick={() => setModal({ type: 'archive', c })}><Archive /></button>)}
                    {can('case:delete') && <button className="btn ghost icon sm" aria-label="Delete case" data-tip="Delete" onClick={() => setModal({ type: 'delete', c })}><Trash2 /></button>}
                  </div>
                </div>
                {c.is_demo && <div style={{ marginTop: 10 }}><Synthetic /></div>}
              </article>
            ))}
          </div>
          <div className="card" style={{ marginTop: 16 }}><Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} /></div>
        </>
      )}
      {modal?.type === 'new' && <CaseForm onClose={() => setModal(null)} onSaved={(c) => navigate(`/app/cases/${c.id}/records`)} />}
      {modal?.type === 'edit' && <CaseForm initial={modal.c} onClose={() => setModal(null)} onSaved={() => reload(true)} />}
      {modal?.type === 'archive' && <Confirm title="Archive case?" message={`${modal.c.name} will be hidden from active views. Records, hashes and the audit trail are kept, and the case can be restored.`}
        confirmLabel="Archive" onClose={() => setModal(null)} onConfirm={async () => { await act(() => api.post(`/cases/${modal.c.id}/archive`), 'Case archived'); setModal(null) }} />}
      {modal?.type === 'delete' && <Confirm danger title="Delete case permanently?" message={`This permanently deletes ${modal.c.name}, its ${modal.c.record_count} records and stored files. The deletion itself is recorded in the audit log.`}
        confirmLabel="Delete permanently" onClose={() => setModal(null)} onConfirm={async () => { await act(() => api.del(`/cases/${modal.c.id}`), 'Case deleted'); setModal(null) }} />}
    </>
  )
}
