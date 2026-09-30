import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, CloudUpload, Fingerprint, XCircle } from 'lucide-react'
import { api, uploadFiles } from '../api'
import { Button, FileIcon, fmtBytes, shortHash, useInterval, useToast } from '../ui'

const ALLOWED = ['pdf', 'jpg', 'jpeg', 'png', 'docx', 'txt']
const STEPS = ['Uploading', 'Securing', 'Hashing', 'Extracting', 'Analyzing', 'Completed']
const DONE = ['Completed', 'Requires Review', 'Failed']

export default function UploadZone({ caseId, maxMb = 20, onUploaded, onRecordDone }) {
  const [drag, setDrag] = useState(false)
  const [items, setItems] = useState([])
  const [busy, setBusy] = useState(false)
  const input = useRef(null)
  const toast = useToast()

  const polling = items.some((i) => i.record && !DONE.includes(i.record.status))
  useInterval(async () => {
    const pending = items.filter((i) => i.record && !DONE.includes(i.record.status))
    for (const it of pending) {
      try {
        const r = await api.get(`/records/${it.record.id}/status`)
        setItems((xs) => xs.map((x) => (x.key === it.key ? { ...x, record: r } : x)))
        if (DONE.includes(r.status)) onRecordDone?.(r)
      } catch { /* retry next tick */ }
    }
  }, 700, polling)

  const accept = async (fileList) => {
    const files = Array.from(fileList || [])
    if (!files.length) return
    const now = Date.now()
    const entries = files.map((f, i) => {
      const ext = f.name.split('.').pop().toLowerCase()
      let error = null
      if (!ALLOWED.includes(ext)) error = 'Unsupported file type. Allowed: PDF, JPG, JPEG, PNG, DOCX, TXT.'
      else if (f.size > maxMb * 1024 * 1024) error = `File exceeds the ${maxMb} MB limit.`
      else if (f.size === 0) error = 'The file is empty.'
      return { key: `${now}-${i}`, file: f, ext, progress: 0, error, record: null }
    })
    setItems((xs) => [...entries, ...xs])
    const valid = entries.filter((e) => !e.error)
    if (!valid.length) return
    setBusy(true)
    try {
      const res = await uploadFiles(caseId, valid.map((v) => v.file), (p) => {
        setItems((xs) => xs.map((x) => (valid.some((v) => v.key === x.key) ? { ...x, progress: p } : x)))
      })
      setItems((xs) => xs.map((x) => {
        const idx = valid.findIndex((v) => v.key === x.key)
        if (idx < 0) return x
        const r = res.results[idx]
        return r.ok ? { ...x, progress: 1, record: r.record } : { ...x, progress: 1, error: r.error || 'Unable to process this file. Please verify the file type and try again.' }
      }))
      const ok = res.results.filter((r) => r.ok).length
      if (ok) toast(`${ok} record${ok > 1 ? 's' : ''} uploaded — analysis pipeline started`, 'success')
      if (ok < res.results.length) toast('Some files were rejected. Please verify the file type and try again.', 'warn')
      onUploaded?.()
    } catch (e) {
      setItems((xs) => xs.map((x) => (valid.some((v) => v.key === x.key) ? { ...x, error: e.message } : x)))
      toast(e.message, 'error')
    } finally { setBusy(false) }
  }

  const stepState = (it, i) => {
    const st = it.error ? 'Failed' : it.record?.status || 'Uploading'
    if (st === 'Failed') return i === 0 ? 'fail' : ''
    if (st === 'Completed' || st === 'Requires Review') return i === 5 ? (st === 'Requires Review' ? 'warn' : 'done') : 'done'
    const cur = STEPS.indexOf(st)
    return i < cur ? 'done' : i === cur ? 'now' : ''
  }

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className={`dropzone ${drag ? 'drag' : ''}`} role="button" tabIndex={0} aria-label="Upload records: drop files here or press Enter to browse"
        onClick={() => input.current?.click()} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), input.current?.click())}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); accept(e.dataTransfer.files) }}>
        <div className="dz-scan" />
        <div className="dz-icon"><CloudUpload /></div>
        <h3 style={{ fontSize: 17 }}>{drag ? 'Release to secure and analyse' : 'Drop records here or click to browse'}</h3>
        <p className="small muted" style={{ marginTop: 6 }}>PDF, JPG, JPEG, PNG, DOCX, TXT · multiple files · up to {maxMb} MB each</p>
        <p className="tiny faint" style={{ marginTop: 10 }}>Each file is validated, stored under an opaque key, fingerprinted with SHA-256, then analysed.</p>
        <input ref={input} type="file" multiple hidden accept=".pdf,.jpg,.jpeg,.png,.docx,.txt" onChange={(e) => { accept(e.target.files); e.target.value = '' }} />
        {busy && <div className="row small" style={{ justifyContent: 'center', marginTop: 12 }}><span className="spinner" />Uploading…</div>}
      </div>
      {items.map((it) => {
        const status = it.error ? 'Failed' : it.record?.status || 'Uploading'
        const stageLabel = it.record?.stage_log?.at(-1)?.label
        return (
          <div key={it.key} className="upload-item">
            <FileIcon ext={it.ext} />
            <div style={{ minWidth: 0 }}>
              <div className="row between" style={{ gap: 10 }}>
                <b className="truncate">{it.file.name}</b>
                <span className="tiny faint" style={{ flex: 'none' }}>{it.ext.toUpperCase()} · {fmtBytes(it.file.size)}</span>
              </div>
              {!it.record && !it.error && <div className="progress" style={{ marginTop: 8 }}><span style={{ width: `${Math.max(4, it.progress * 100)}%` }} /></div>}
              <div className="stepper" aria-label={`Processing status: ${status}`}>
                {STEPS.map((s, i) => <span key={s} className={stepState(it, i)}>{i === 5 && status === 'Requires Review' ? 'Requires Review' : s}</span>)}
              </div>
              {it.error && <div className="form-error" style={{ marginTop: 6 }} role="alert">{it.error}</div>}
              {it.record && !DONE.includes(status) && stageLabel && <div className="tiny" style={{ marginTop: 6, color: 'var(--cyan-2)' }}>{stageLabel}…</div>}
              {it.record?.sha256 && <div className="row tiny mono" style={{ marginTop: 6, color: 'var(--cyan-2)', gap: 6 }}><Fingerprint size={12} />SHA-256 {shortHash(it.record.sha256)}</div>}
              {it.record?.status === 'Failed' && <div className="form-error" style={{ marginTop: 6 }}>{it.record.error}</div>}
            </div>
            <div>
              {status === 'Completed' && <CheckCircle2 color="var(--green-2)" aria-label="Completed" />}
              {status === 'Failed' && <XCircle color="var(--red-2)" aria-label="Failed" />}
              {status === 'Requires Review' && <Link className="btn sm warn" to={`/app/records/${it.record.id}`}>Review</Link>}
              {status === 'Completed' && it.record && <Link className="btn sm ghost" to={`/app/records/${it.record.id}`}>Open</Link>}
              {!DONE.includes(status) && <span className="spinner" aria-label="Processing" />}
            </div>
          </div>
        )
      })}
      {items.length > 0 && !busy && !polling && <div className="row"><Button size="sm" variant="ghost" onClick={() => setItems([])}>Clear list</Button></div>}
    </div>
  )
}
