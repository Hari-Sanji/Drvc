import { useEffect, useRef, useState } from 'react'
import {
  AlertOctagon, CalendarClock, CheckCircle2, Circle, CloudUpload, Database, FileSignature, Fingerprint, Lock, ScanText,
  ShieldCheck, Sparkles, Tags,
} from 'lucide-react'
import { api } from '../api'
import { Button, CopyButton, fmtBytes } from '../ui'

const STAGES = [
  ['Validating file signature', Lock],
  ['Generating SHA-256', Fingerprint],
  ['Reading metadata & signatures', Database],
  ['Extracting text / running OCR', ScanText],
  ['Finding entities & events', Tags],
  ['Checking for signals', ShieldCheck],
]
const ENTITY_LABEL = { PERSON: 'Person', ORG: 'Organization', LOCATION: 'Location', ID: 'Identifier', DOC_REF: 'Document ref', DATE: 'Date', AMOUNT: 'Amount' }

/** Public, login-free analysis of a single file. The server stores nothing. */
export default function TryIt({ onLaunchDemo }) {
  const [drag, setDrag] = useState(false)
  const [file, setFile] = useState(null)
  const [step, setStep] = useState(-1)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState('')
  const input = useRef(null)
  const timer = useRef(null)
  useEffect(() => () => clearInterval(timer.current), [])

  const run = async (f) => {
    if (!f) return
    setErr(''); setRes(null); setFile(f)
    const ext = f.name.split('.').pop().toLowerCase()
    if (!['pdf', 'jpg', 'jpeg', 'png', 'docx', 'txt'].includes(ext)) { setErr('Unsupported file type. Allowed: PDF, JPG, JPEG, PNG, DOCX, TXT.'); return }
    if (f.size > 5 * 1024 * 1024) { setErr('For the public demo, files are limited to 5 MB. Sign in to analyse larger files.'); return }
    setStep(0)
    clearInterval(timer.current)
    timer.current = setInterval(() => setStep((s) => Math.min(s + 1, STAGES.length - 1)), 520)
    try {
      const fd = new FormData(); fd.append('file', f)
      const r = await api.post('/public/analyze', fd)
      clearInterval(timer.current)
      for (let s = 0; s <= STAGES.length; s++) { setStep(s); await new Promise((ok) => setTimeout(ok, 140)) }
      setRes(r)
    } catch (e) {
      clearInterval(timer.current); setStep(-1); setErr(e.message)
    }
  }
  const groups = res ? res.entities.reduce((a, e) => ({ ...a, [e.type]: [...(a[e.type] || []), e.value] }), {}) : {}
  const signals = res ? [
    ...res.signatures.map((s) => ({ key: s.field, tone: s.intact === false ? 'high' : 'low', icon: FileSignature,
      title: `Digital signature — ${s.intact === true ? 'signed bytes intact' : s.intact === false ? 'changed after signing' : 'not checked'}`,
      detail: `${s.signer || 'Unknown signer'}${s.trusted ? '' : ' · certificate not from a trusted authority'}` })),
    ...res.flags.map((f) => ({ key: f.code, tone: f.severity, icon: AlertOctagon, title: f.title, detail: `${f.value_a} · ${f.value_b}` })),
  ] : []

  return (
    <section className="try-zone" aria-label="Try it with your own file">
      <div className="card glow-border" style={{ padding: 22 }}>
        <div className="row wrap between" style={{ marginBottom: 14, gap: 10 }}>
          <div>
            <div className="page-head" style={{ margin: 0 }}><div><div className="eyebrow"><Sparkles size={14} />No sign-in needed</div><h2>Try it with your own file</h2></div></div>
            <p className="small muted" style={{ marginTop: 4 }}>See the single-record pipeline on any PDF, image, DOCX or TXT (max 5 MB). <b>Nothing is stored</b> — the file is analysed in memory and discarded.</p>
          </div>
          {res && <Button size="sm" onClick={() => { setRes(null); setFile(null); setStep(-1) }}>Try another file</Button>}
        </div>

        {!res && step < 0 && (
          <div className={`dropzone ${drag ? 'drag' : ''}`} role="button" tabIndex={0} aria-label="Choose a file to analyse"
            onClick={() => input.current?.click()} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), input.current?.click())}
            onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); run(e.dataTransfer.files[0]) }} style={{ padding: '26px 20px' }}>
            <div className="dz-scan" />
            <div className="dz-icon" style={{ width: 54, height: 54 }}><CloudUpload /></div>
            <h3 style={{ fontSize: 16 }}>{drag ? 'Release to analyse' : 'Drop a file here or click to choose'}</h3>
            <p className="tiny faint" style={{ marginTop: 6 }}>PDF · JPG · PNG · DOCX · TXT</p>
            <input ref={input} type="file" hidden accept=".pdf,.jpg,.jpeg,.png,.docx,.txt" onChange={(e) => { run(e.target.files[0]); e.target.value = '' }} />
          </div>
        )}
        {err && <div className="form-error" role="alert" style={{ marginTop: 10 }}>{err}</div>}

        {step >= 0 && !res && (
          <div className="grid g2" style={{ alignItems: 'center' }} aria-live="polite">
            <div className="stack" style={{ gap: 8 }}>
              <b className="small">{file?.name}</b>
              {STAGES.map(([label, I], i) => (
                <div key={label} className="row small" style={{ opacity: i <= step ? 1 : 0.4, transition: 'opacity .3s' }}>
                  {i < step ? <CheckCircle2 size={16} color="var(--green-2)" /> : i === step ? <span className="spinner" style={{ width: 16, height: 16 }} /> : <Circle size={16} color="var(--text-3)" />}
                  <I size={15} color="var(--text-3)" />{label}
                </div>
              ))}
            </div>
            <p className="small muted">Running the same deterministic pipeline the platform uses — no external AI service, no storage.</p>
          </div>
        )}

        {res && (
          <div className="try-result stack" style={{ gap: 14 }}>
            <div className="row wrap" style={{ gap: 8 }}>
              <span className="badge b-violet">{res.file.doc_type}</span>
              <span className="badge b-neutral">{res.file.type} · {fmtBytes(res.file.size)}</span>
              <span className="badge b-neutral"><ScanText />{res.text.method}</span>
              {res.text.confidence != null && <span className="badge b-green">OCR confidence {Math.round(res.text.confidence)}%</span>}
              <span className="badge b-green"><Lock />Not stored</span>
            </div>
            <div>
              <div className="label" style={{ marginBottom: 6 }}>SHA-256 fingerprint</div>
              <div className="hash"><Fingerprint size={16} style={{ flex: 'none' }} /><span className="grow">{res.sha256}</span><CopyButton text={res.sha256} /></div>
            </div>
            <div className="grid g2">
              <div>
                <div className="label" style={{ marginBottom: 8 }}>Entities found</div>
                {res.entities.length === 0 ? <p className="small muted">No entities detected{res.text.error ? ` — ${res.text.error}` : '.'}</p> : (
                  <div className="stack" style={{ gap: 8 }}>
                    {Object.entries(groups).map(([t, vals]) => (
                      <div key={t} className="row wrap" style={{ gap: 6 }}>
                        {vals.slice(0, 8).map((v) => <div key={v} className={`entity e-${t}`}><span className="etype">{ENTITY_LABEL[t]}</span><span className="evalue">{v}</span></div>)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="stack" style={{ gap: 12 }}>
                <div>
                  <div className="label" style={{ marginBottom: 8 }}>Events</div>
                  {res.events.length === 0 ? <p className="small muted">No dated events detected.</p> : res.events.slice(0, 6).map((e) => (
                    <div key={e.date + e.label} className="row small" style={{ gap: 8, marginBottom: 4 }}><CalendarClock size={14} color="var(--cyan-2)" /><b style={{ color: 'var(--cyan-2)' }}>{e.date_label}</b>{e.label}</div>
                  ))}
                </div>
                <div>
                  <div className="label" style={{ marginBottom: 8 }}>Signals</div>
                  {signals.length === 0 ? <p className="small muted">No metadata or signature signals. {res.metadata.available.length} metadata properties read{res.metadata.not_available.length ? `; not available: ${res.metadata.not_available.join(', ').toLowerCase()}` : ''}.</p>
                    : signals.map((s) => { const I = s.icon; return <div key={s.key} className={`flag-row ${s.tone}`}><I size={15} style={{ flex: 'none', marginTop: 1 }} /><div><b>{s.title}</b><div className="tiny faint">{s.detail}</div></div></div> })}
                </div>
              </div>
            </div>
            {res.text.excerpt && (
              <details className="why"><summary><ScanText size={15} />Extracted text ({res.text.length.toLocaleString()} characters)</summary>
                <div className="why-body"><div className="textbox" style={{ maxHeight: 220 }}>{res.text.excerpt}{res.text.length > res.text.excerpt.length ? '…' : ''}</div></div></details>
            )}
            <div className="principle" style={{ justifyContent: 'space-between', flexWrap: 'wrap' }}>
              <span>Relationships, timelines and conflicts need <b>several records from one case</b>. See them in the guided demo.</span>
              <Button size="sm" variant="primary" onClick={onLaunchDemo}>Launch Demo</Button>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
