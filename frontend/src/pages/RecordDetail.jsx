import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import {
  AlertOctagon, CalendarClock, CheckCircle2, ClipboardList, Cpu, Database, Download, FileQuestion, Fingerprint, Info, Link2,
  FileSignature, ListChecks, MessageSquarePlus, ScanText, ScrollText, ShieldCheck, ShieldQuestion, Tags,
} from 'lucide-react'
import { api, downloadFile } from '../api'
import { useAuth } from '../auth'
import { ConflictCard } from '../components/Conflicts'
import {
  Button, CopyButton, Empty, ErrorState, FileIcon, Loading, Principle, StatusBadge, Synthetic, fmtBytes, fmtDateTime, fmtIsoDate, timeAgo,
  useAsync, useToast,
} from '../ui'

const ENTITY_LABEL = { PERSON: 'Person', ORG: 'Organization', LOCATION: 'Location', ID: 'Identifier', DOC_REF: 'Document reference', DATE: 'Date', AMOUNT: 'Amount' }

function Highlighted({ text, entities }) {
  const parts = useMemo(() => {
    const spans = entities.filter((e) => e.start >= 0 && e.end > e.start && text.slice(e.start, e.end)).sort((a, b) => a.start - b.start || b.end - a.end)
    const out = []; let pos = 0
    for (const e of spans) {
      if (e.start < pos) continue
      if (e.start > pos) out.push(text.slice(pos, e.start))
      out.push(<mark key={`${e.id}`} className={`hl e-${e.type}`} title={`${ENTITY_LABEL[e.type]}${e.label ? ` · ${e.label}` : ''}`}>{text.slice(e.start, e.end)}</mark>)
      pos = e.end
    }
    out.push(text.slice(pos))
    return out
  }, [text, entities])
  return <div className="textbox" tabIndex={0} aria-label="Extracted text with highlighted entities">{parts}</div>
}

function Preview({ record }) {
  const [url, setUrl] = useState(null)
  const [err, setErr] = useState(false)
  const previewable = record.kind === 'image' || record.ext === 'PDF'
  useEffect(() => {
    if (!previewable) return
    let u
    api.blob(`/records/${record.id}/file`).then((b) => { u = URL.createObjectURL(b); setUrl(u) }).catch(() => setErr(true))
    return () => u && URL.revokeObjectURL(u)
  }, [record.id, previewable])
  const dl = () => downloadFile(`/records/${record.id}/file?download=true`, record.filename)
  if (!previewable) return (
    <div className="empty" style={{ padding: 30 }}>
      <FileIcon ext={record.ext} size={56} />
      <p className="small">An inline preview is not rendered for {record.ext} files. The extracted text is shown alongside.</p>
      <Button size="sm" icon={Download} onClick={dl}>Download original</Button>
    </div>
  )
  if (err) return <p className="small muted" style={{ padding: 20 }}>The original file could not be loaded for preview.</p>
  if (!url) return <div className="center-load"><span className="spinner" /></div>
  return (
    <div className="stack" style={{ gap: 8 }}>
      {record.kind === 'image'
        ? <img src={url} alt={`Original record: ${record.filename}`} style={{ width: '100%', borderRadius: 12, border: '1px solid var(--border)', background: '#fff' }} />
        : <iframe src={url} title={`Original record: ${record.filename}`} style={{ width: '100%', height: 520, border: '1px solid var(--border)', borderRadius: 12, background: '#fff' }} />}
      <Button size="sm" icon={Download} onClick={dl}>Download original</Button>
    </div>
  )
}

function Signatures({ sigs }) {
  if (!sigs.length) return <div className="sig"><div className="row small"><FileSignature size={16} color="var(--text-3)" /><b>No digital signature</b></div><p className="tiny faint" style={{ marginTop: 4 }}>This PDF has no embedded digital signature. Many genuine documents are unsigned.</p></div>
  return sigs.map((g) => {
    const cls = g.intact === true ? 'ok' : g.intact === false ? 'bad' : ''
    return (
      <div key={g.field} className={`sig ${cls}`}>
        <div className="row between wrap">
          <div className="row small"><FileSignature size={16} color={g.intact === false ? 'var(--red-2)' : 'var(--green-2)'} /><b>Digital signature</b></div>
          {g.intact === true && <span className="badge b-green"><ShieldCheck />Signed bytes intact</span>}
          {g.intact === false && <span className="badge b-red pulse-red"><AlertOctagon />Changed after signing</span>}
          {g.intact == null && <span className="badge b-neutral">Not cryptographically checked</span>}
        </div>
        <div className="kv" style={{ marginTop: 8 }}>
          <div>Signer</div><div>{g.signer || '—'}{g.organization && <span className="faint"> · {g.organization}</span>}</div>
          <div>Signed at</div><div>{fmtDateTime(g.signed_at)}</div>
          {g.reason && <><div>Reason</div><div>{g.reason}</div></>}
          {g.location && <><div>Location</div><div>{g.location}</div></>}
          <div>Coverage</div><div>{g.coverage || '—'}</div>
          <div>Certificate trust</div><div>{g.trusted ? 'Chains to a trusted authority' : 'Not from a trusted authority (e.g. self-signed) — identity not confirmed'}</div>
        </div>
        <p className="tiny faint" style={{ marginTop: 6 }}>{g.method}. An intact signature shows the signed bytes are unchanged; it does not by itself confirm who the signer is.</p>
      </div>
    )
  })
}

function Section({ id, icon: I, title, children, right }) {
  return (
    <section id={id} className="card" style={{ scrollMarginTop: 90 }}>
      <div className="card-head"><h3><I />{title}</h3>{right}</div>
      <div className="card-body">{children}</div>
    </section>
  )
}

export default function RecordDetail() {
  const { id } = useParams()
  const loc = useLocation()
  const navigate = useNavigate()
  const { can } = useAuth()
  const toast = useToast()
  const { data, error, reload } = useAsync(() => api.get(`/records/${id}`), [id])
  const [verify, setVerify] = useState(null)
  const [note, setNote] = useState('')

  useEffect(() => {
    if (data && loc.hash) setTimeout(() => document.querySelector(loc.hash)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 150)
  }, [data, loc.hash])

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (!data) return <Loading label="Loading record…" />
  const r = data.record
  const md = data.metadata
  const groups = data.entities.reduce((a, e) => ({ ...a, [e.type]: [...(a[e.type] || []), e] }), {})
  const doVerify = async () => {
    setVerify({ busy: true })
    try { setVerify(await api.post(`/records/${id}/verify`)) } catch (e) { toast(e.message, 'error'); setVerify(null) }
  }
  const addNote = async () => {
    if (note.trim().length < 3) return toast('Please write at least 3 characters.', 'warn')
    try { await api.post(`/cases/${data.case.id}/notes`, { note, record_id: r.id }); setNote(''); toast('Note added', 'success'); reload(true) } catch (e) { toast(e.message, 'error') }
  }
  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="card pad glow-border">
        <div className="row wrap" style={{ gap: 16 }}>
          <FileIcon ext={r.ext} size={52} />
          <div className="grow">
            <div className="row wrap small muted" style={{ gap: 8 }}>
              <Link to={`/app/cases/${data.case.id}/records`}>{data.case.code}</Link><span>/</span><span>{data.case.name}</span>{r.is_demo && <Synthetic />}
            </div>
            <h1 style={{ fontSize: 24, marginTop: 4, wordBreak: 'break-word' }}>{r.filename}</h1>
            <div className="row wrap" style={{ marginTop: 8 }}>
              <StatusBadge status={r.status} /><span className="badge b-violet">{r.doc_type}</span><span className="badge b-neutral">{r.ext} · {fmtBytes(r.size)}</span>
              {data.conflicts.some((c) => ['requires_review', 'escalated'].includes(c.status)) && <span className="badge b-red pulse-red"><AlertOctagon />Potential inconsistency detected</span>}
              {r.sha256 && <span className="badge b-cyan"><ShieldCheck />Integrity information available</span>}
            </div>
          </div>
        </div>
        <nav className="tabs" style={{ marginTop: 16 }} aria-label="Record sections">
          {[['integrity', 'Integrity'], ['metadata', 'Metadata'], ['extracted', 'Extracted information'], ['events', 'Events'], ['relationships', 'Relationships'], ['conflicts', 'Conflicts'], ['history', 'Review & audit']].map(([h, l]) => (
            <a key={h} href={`#${h}`} onClick={(e) => { e.preventDefault(); navigate(`#${h}`, { replace: true }); document.getElementById(h)?.scrollIntoView({ behavior: 'smooth' }) }}>{l}</a>
          ))}
        </nav>
      </div>

      <div className="grid g2">
        <Section id="integrity" icon={Fingerprint} title="File information & integrity">
          <div className="kv">
            <div>Filename</div><div style={{ wordBreak: 'break-all' }}>{r.filename}</div>
            <div>File type</div><div>{r.ext} · {r.mime}</div>
            <div>File size</div><div>{fmtBytes(r.size)} ({r.size.toLocaleString()} bytes)</div>
            <div>Uploaded</div><div>{fmtDateTime(r.uploaded_at)}{r.uploaded_by && <span className="faint"> by {r.uploaded_by}</span>}</div>
            <div>Hashed</div><div>{fmtDateTime(r.hashed_at)}</div>
            <div>Processed</div><div>{fmtDateTime(r.processed_at)}</div>
          </div>
          <div className="label" style={{ margin: '16px 0 8px' }}>SHA-256</div>
          <div className="hash"><Fingerprint size={16} style={{ flex: 'none' }} /><span className="grow">{r.sha256 || 'Not generated'}</span></div>
          <div className="row wrap" style={{ marginTop: 10 }}>
            {r.sha256 && <CopyButton text={r.sha256} label="Copy hash" />}
            {r.sha256 && <Button size="sm" icon={ShieldCheck} loading={verify?.busy} onClick={doVerify}>Re-verify stored file</Button>}
          </div>
          {verify && !verify.busy && (
            <div className="chip" style={{ marginTop: 10, borderColor: verify.match ? 'rgba(16,185,129,.4)' : 'rgba(244,63,94,.4)', display: 'flex' }}>
              {verify.match ? <CheckCircle2 size={16} color="var(--green-2)" /> : <AlertOctagon size={16} color="var(--red-2)" />}
              <span className="small">{verify.match ? 'Stored content matches the recorded fingerprint' : 'Stored content differs from the recorded fingerprint'} · checked {timeAgo(verify.checked_at)}</span>
            </div>
          )}
          <p className="tiny faint" style={{ marginTop: 12 }}><Info size={12} style={{ verticalAlign: -2 }} /> SHA-256 provides a content fingerprint and helps identify changes to file content relative to the recorded hash. It does not prove the real-world truth of the document.</p>
          {r.ext === 'PDF' && <Signatures sigs={md.signatures || []} />}
        </Section>

        <Section id="metadata" icon={Database} title="Metadata">
          <div className="label" style={{ marginBottom: 8 }}>Available metadata</div>
          {md.available.length === 0 ? <p className="small muted">No readable metadata was available.</p> : (
            <div className="kv">{md.available.map((m) => [<div key={m.key + 'k'}>{m.label}</div>, <div key={m.key + 'v'} style={{ wordBreak: 'break-word' }}>{m.value}</div>])}</div>
          )}
          <div className="label" style={{ margin: '16px 0 8px' }}>Metadata not available</div>
          {md.not_available.length === 0 ? <p className="small muted">All standard properties were present.</p> : (
            <div className="row wrap" style={{ gap: 6 }}>{md.not_available.map((x) => <span key={x} className="badge b-neutral"><FileQuestion />{x}</span>)}</div>
          )}
          {md.notes?.map((n) => <p key={n} className="tiny faint" style={{ marginTop: 10 }}><Info size={12} style={{ verticalAlign: -2 }} /> {n}</p>)}
          {(md.flags || []).length > 0 && <>
            <div className="label" style={{ margin: '16px 0 4px' }}>Metadata signals</div>
            {md.flags.map((f) => (
              <div key={f.code} className={`flag-row ${f.severity}`}>
                <AlertOctagon size={16} color={f.severity === 'high' ? 'var(--red-2)' : f.severity === 'medium' ? 'var(--amber-2)' : 'var(--text-3)'} style={{ flex: 'none', marginTop: 1 }} />
                <div><b>{f.title}</b> <span className="tiny faint">· {f.severity}</span><div className="small muted">{f.value_a} · {f.value_b}</div><div className="tiny faint" style={{ marginTop: 3 }}>{f.detail}</div></div>
              </div>
            ))}
          </>}
          <p className="tiny faint" style={{ marginTop: 10 }}>Metadata is shown exactly as read from the file — nothing is inferred or fabricated. Missing metadata is never treated as suspicious.</p>
        </Section>
      </div>

      <Section id="extracted" icon={ScanText} title="Extracted text & original preview" right={
        <div className="row wrap" style={{ gap: 6 }}>
          <span className="badge b-neutral"><Cpu />{data.text_method}</span>
          {data.ocr_confidence != null && <span className={`badge ${data.ocr_confidence >= 80 ? 'b-green' : 'b-amber'}`}>OCR Confidence: {Math.round(data.ocr_confidence)}%</span>}
        </div>}>
        {r.error && <div className="principle" style={{ marginBottom: 14, borderColor: 'rgba(244,63,94,.3)' }}><AlertOctagon color="var(--red-2)" />{r.error}</div>}
        <div className="grid g2">
          <div><div className="label" style={{ marginBottom: 8 }}>Original record</div><Preview record={r} /></div>
          <div>
            <div className="label" style={{ marginBottom: 8 }}>Extracted text</div>
            {data.text ? <Highlighted text={data.text} entities={data.entities} /> : <p className="small muted">No text could be extracted. The original record is still available for manual review.</p>}
            <div className="row wrap tiny" style={{ marginTop: 10, gap: 6 }}>
              {Object.keys(ENTITY_LABEL).map((t) => <span key={t} className={`badge e-${t}`} style={{ border: '1px solid' }}>{ENTITY_LABEL[t]}</span>)}
            </div>
          </div>
        </div>
        <div className="grid g2" style={{ marginTop: 18 }}>
          <div>
            <div className="label" style={{ marginBottom: 10 }}><Tags size={13} style={{ verticalAlign: -2 }} /> Entities</div>
            {data.entities.length === 0 ? <p className="small muted">No entities were detected.</p> : (
              <div className="stack" style={{ gap: 12 }}>
                {Object.entries(groups).map(([t, es]) => (
                  <div key={t} className="row wrap" style={{ gap: 8 }}>
                    {es.map((e) => (
                      <div key={e.id} className={`entity e-${t}`} title={`Confidence ${Math.round(e.confidence * 100)}%`}>
                        <span className="etype">{ENTITY_LABEL[t]}</span><span className="evalue">{e.value}</span>{e.label && <span className="elabel">{e.label}</span>}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
          <div>
            <div className="label" style={{ marginBottom: 10 }}><ListChecks size={13} style={{ verticalAlign: -2 }} /> Labelled fields</div>
            {Object.keys(data.fields).length === 0 ? <p className="small muted">No labelled fields (e.g. “Name: …”) were recognised.</p> : (
              <div className="kv">{Object.entries(data.fields).map(([k, f]) => [<div key={k + 'k'}>{f.label}</div>, <div key={k + 'v'}><b>{f.raw}</b> <span className="tiny faint">“{f.source_label}”</span></div>])}</div>
            )}
          </div>
        </div>
      </Section>

      <div className="grid g2">
        <Section id="events" icon={CalendarClock} title="Events & timeline presence">
          {data.events.length === 0 ? <p className="small muted">No dated events were extracted from this record.</p> : (
            <>
              <div style={{ position: 'relative', height: 26, margin: '4px 0 14px' }} aria-label="Position of this record's events within the case timeline">
                <div style={{ position: 'absolute', top: 12, left: 0, right: 0, height: 2, background: 'var(--border-strong)', borderRadius: 2 }} />
                {data.events.filter((e) => e.position != null).map((e) => (
                  <span key={e.id} title={`${e.label} · ${fmtIsoDate(e.date)}`} style={{ position: 'absolute', top: 6, left: `calc(${(e.position / Math.max(1, data.timeline_size - 1)) * 100}% - 7px)`, width: 14, height: 14, borderRadius: '50%',
                    background: e.flag === 'conflict' ? 'var(--red)' : 'var(--cyan)', boxShadow: `0 0 10px ${e.flag === 'conflict' ? 'var(--red)' : 'var(--cyan)'}` }} />
                ))}
              </div>
              <p className="tiny faint" style={{ marginBottom: 10 }}>{data.events.length} of {data.timeline_size} case timeline events come from this record.</p>
              <div className="stack" style={{ gap: 8 }}>
                {data.events.map((e) => (
                  <Link key={e.id} to={`/app/cases/${data.case.id}/timeline`} className="chip" style={{ color: 'var(--text)', textDecoration: 'none', justifyContent: 'space-between', borderColor: e.flag === 'conflict' ? 'rgba(244,63,94,.45)' : undefined }}>
                    <span><b className="small" style={{ color: e.flag === 'conflict' ? 'var(--red-2)' : 'var(--cyan-2)' }}>{fmtIsoDate(e.date)}</b> — {e.label}</span>
                    {e.flag === 'conflict' && <span className="badge b-red">Conflicting date</span>}
                  </Link>
                ))}
              </div>
            </>
          )}
        </Section>
        <Section id="relationships" icon={Link2} title="Relationships">
          {data.relationships.length === 0 ? <p className="small muted">No significant relationship signals detected.</p> : (
            <div className="stack" style={{ gap: 8 }}>
              {data.relationships.map((x) => {
                const other = x.source.id === r.id ? x.target : x.source
                return (
                  <Link key={x.id} to={`/app/records/${other.id}`} className="chip" style={{ color: 'var(--text)', textDecoration: 'none', display: 'block' }}>
                    <div className="row between"><b className="small">{other.doc_type}</b><span className={`badge ${x.score >= 0.75 ? 'b-cyan' : 'b-violet'}`}>{x.label} · {Math.round(x.score * 100)}%</span></div>
                    <div className="tiny faint truncate">{other.filename}</div>
                    <div className="tiny muted" style={{ marginTop: 4 }}>{x.evidence.slice(0, 3).map((e) => `${e.type}: ${e.value}`).join(' · ')}</div>
                  </Link>
                )
              })}
            </div>
          )}
        </Section>
      </div>

      <section id="conflicts" style={{ scrollMarginTop: 90 }} className="stack">
        <h2 className="row" style={{ fontSize: 17 }}><AlertOctagon size={18} color="var(--red-2)" />Conflicts involving this record</h2>
        {data.conflicts.length === 0 ? <div className="card"><Empty icon={ShieldCheck} title="No potential inconsistencies detected" /></div>
          : data.conflicts.map((c) => <ConflictCard key={c.id} c={c} onChanged={() => reload(true)} />)}
      </section>

      <div id="history" className="grid g2" style={{ scrollMarginTop: 90 }}>
        <Section id="reviews" icon={ClipboardList} title="Review history">
          {can('review:note') && (
            <div className="row" style={{ marginBottom: 14, alignItems: 'stretch' }}>
              <input className="input" placeholder="Add a review note about this record…" aria-label="Review note" value={note} onChange={(e) => setNote(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addNote()} />
              <Button icon={MessageSquarePlus} onClick={addNote}>Add</Button>
            </div>
          )}
          {data.reviews.length === 0 ? <p className="small muted">No review actions yet.</p> : (
            <div className="stack" style={{ gap: 8 }}>
              {data.reviews.map((h) => (
                <div key={h.id} className="chip" style={{ display: 'block' }}>
                  <div className="row between"><b className="small">{h.user} <span className="faint" style={{ fontWeight: 500 }}>· {h.role}</span></b><span className="tiny faint">{fmtDateTime(h.at)}</span></div>
                  <div className="small">{h.action.replace('_', ' ')} <span className="faint">· {h.subject}</span></div>
                  {h.note && <div className="small muted">“{h.note}”</div>}
                </div>
              ))}
            </div>
          )}
        </Section>
        <Section id="audit" icon={ScrollText} title="Audit history & pipeline">
          <div className="stack" style={{ gap: 0, maxHeight: 420, overflowY: 'auto' }}>
            {data.audit.map((a) => (
              <div key={a.id} className="feed-item">
                <div className={`feed-ic ${a.result === 'success' ? 'ic-cyan' : 'ic-red'}`}>{a.result === 'success' ? <CheckCircle2 /> : <ShieldQuestion />}</div>
                <div className="grow" style={{ minWidth: 0 }}>
                  <div className="small" style={{ fontWeight: 600 }}>{a.action}</div>
                  <div className="tiny faint" style={{ wordBreak: 'break-word' }}>{a.user} · {fmtDateTime(a.ts)}{a.details && ` · ${a.details.slice(0, 140)}`}</div>
                </div>
              </div>
            ))}
          </div>
        </Section>
      </div>
      <Principle />
    </div>
  )
}

