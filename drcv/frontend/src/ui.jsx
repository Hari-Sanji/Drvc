import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  AlertTriangle, ArrowRight, Check, CheckCircle2, Copy, FileSearch, Info, Link2, Network, ScanSearch, Shuffle,
  UserCheck, X, XCircle,
} from 'lucide-react'

/* ------------------------------------------------------------------ formatting */
export const fmtBytes = (n) => {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}
export const fmtDate = (s) => s ? new Date(s).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
export const fmtDateTime = (s) => s ? new Date(s).toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
export const fmtIsoDate = (iso) => {
  if (!iso) return '—'
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' })
}
export function timeAgo(s) {
  if (!s) return ''
  const sec = Math.round((Date.now() - new Date(s).getTime()) / 1000)
  if (sec < 45) return 'just now'
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`
  if (sec < 86400) return `${Math.round(sec / 3600)}h ago`
  if (sec < 86400 * 30) return `${Math.round(sec / 86400)}d ago`
  return fmtDate(s)
}
export const shortHash = (h) => (h ? `${h.slice(0, 8)}…${h.slice(-6)}` : '—')

/* ------------------------------------------------------------------ hooks */
export function useAsync(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const seq = useRef(0)
  const run = useCallback(async (silent = false) => {
    const id = ++seq.current
    if (!silent) setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const data = await fn()
      if (id === seq.current) setState({ data, error: null, loading: false })
      return data
    } catch (e) {
      if (id === seq.current) setState((s) => ({ data: silent ? s.data : null, error: e, loading: false }))
    }
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { run() }, [run])
  return { ...state, reload: run, setData: (d) => setState((s) => ({ ...s, data: typeof d === 'function' ? d(s.data) : d })) }
}

export function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value)
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t) }, [value, ms])
  return v
}

export function useInterval(fn, ms, active = true) {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    if (!active) return
    const t = setInterval(() => ref.current(), ms)
    return () => clearInterval(t)
  }, [ms, active])
}

/* ------------------------------------------------------------------ button with ripple */
export function Button({ children, variant = '', size = '', icon: Icon, iconRight: IconR, loading, className = '', onClick, type = 'button', ...rest }) {
  const handle = (e) => {
    const b = e.currentTarget
    const r = b.getBoundingClientRect()
    const d = Math.max(r.width, r.height)
    const s = document.createElement('span')
    s.className = 'ripple'
    s.style.cssText = `width:${d}px;height:${d}px;left:${e.clientX - r.left - d / 2}px;top:${e.clientY - r.top - d / 2}px`
    b.appendChild(s)
    setTimeout(() => s.remove(), 650)
    onClick?.(e)
  }
  return (
    <button type={type} className={`btn ${variant} ${size} ${className}`} onClick={handle} disabled={loading || rest.disabled} {...rest}>
      {loading ? <span className="spinner" style={{ width: 15, height: 15 }} /> : Icon && <Icon aria-hidden />}
      {children}
      {IconR && !loading && <IconR aria-hidden />}
    </button>
  )
}

/* ------------------------------------------------------------------ toasts */
const ToastCtx = createContext(() => {})
export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const push = useCallback((message, type = 'success', ms = 4200) => {
    const id = Math.random().toString(36).slice(2)
    setItems((xs) => [...xs, { id, message, type }])
    setTimeout(() => setItems((xs) => xs.map((x) => (x.id === id ? { ...x, out: true } : x))), ms)
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), ms + 320)
  }, [])
  const icons = { success: CheckCircle2, error: XCircle, info: Info, warn: AlertTriangle }
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => {
          const I = icons[t.type] || Info
          return (
            <div key={t.id} className={`toast ${t.type} ${t.out ? 'out' : ''}`}>
              <I aria-hidden />
              <div className="grow">{t.message}</div>
              <button className="btn ghost icon sm" style={{ height: 22, width: 22 }} aria-label="Dismiss" onClick={() => setItems((xs) => xs.filter((x) => x.id !== t.id))}><X /></button>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}
export const useToast = () => useContext(ToastCtx)

/* ------------------------------------------------------------------ modal */
export function Modal({ title, icon: Icon, onClose, children, footer, size = '' }) {
  const ref = useRef(null)
  useEffect(() => {
    const prev = document.activeElement
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.()
      if (e.key === 'Tab' && ref.current) {
        const f = ref.current.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
        if (!f.length) return
        const first = f[0]; const last = f[f.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', onKey)
    setTimeout(() => ref.current?.querySelector('input, textarea, select, button.primary, button')?.focus(), 30)
    return () => { document.removeEventListener('keydown', onKey); prev?.focus?.() }
  }, [onClose])
  return createPortal(
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div className={`modal ${size}`} role="dialog" aria-modal="true" aria-label={typeof title === 'string' ? title : 'Dialog'} ref={ref}>
        <div className="modal-head">
          <h2 className="row" style={{ fontSize: 17 }}>{Icon && <Icon size={18} className="gradient-icon" />}{title}</h2>
          <button className="btn ghost icon sm" onClick={onClose} aria-label="Close dialog"><X /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}

export function Confirm({ title, message, confirmLabel = 'Confirm', danger, onConfirm, onClose }) {
  const [busy, setBusy] = useState(false)
  return (
    <Modal title={title} onClose={onClose} footer={<>
      <Button variant="ghost" onClick={onClose}>Cancel</Button>
      <Button variant={danger ? 'danger' : 'primary'} loading={busy} onClick={async () => { setBusy(true); try { await onConfirm() } finally { setBusy(false) } }}>{confirmLabel}</Button>
    </>}>
      <p className="muted">{message}</p>
    </Modal>
  )
}

/* ------------------------------------------------------------------ small components */
export const Skeleton = ({ h = 16, w = '100%', r, style }) => <div className="skeleton" style={{ height: h, width: w, borderRadius: r, ...style }} />

export function SkeletonCards({ n = 3, h = 120 }) {
  return <div className="grid g3">{Array.from({ length: n }).map((_, i) => <div key={i} className="card pad"><Skeleton h={14} w="40%" /><Skeleton h={h - 60} style={{ marginTop: 14 }} /></div>)}</div>
}

export function Empty({ icon: Icon = FileSearch, title, children, action }) {
  return (
    <div className="empty">
      <div className="empty-icon"><Icon aria-hidden /></div>
      {title && <h3>{title}</h3>}
      {children && <p className="small" style={{ maxWidth: 440 }}>{children}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="empty">
      <div className="empty-icon" style={{ color: 'var(--red-2)' }}><AlertTriangle aria-hidden /></div>
      <h3>{error?.status === 403 ? 'Access restricted' : 'Something went wrong'}</h3>
      <p className="small">{error?.message || 'Please try again.'}</p>
      {onRetry && error?.status !== 403 && <Button size="sm" onClick={() => onRetry()}>Retry</Button>}
    </div>
  )
}

export function Loading({ label = 'Loading…' }) {
  return <div className="center-load"><div className="row muted"><span className="spinner" />{label}</div></div>
}

export function Counter({ value = 0, duration = 1100 }) {
  const [n, setN] = useState(0)
  const from = useRef(0)
  useEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduce) { setN(value); from.current = value; return }
    const start = performance.now(); const a = from.current
    let raf
    const tick = (t) => {
      const p = Math.min(1, (t - start) / duration)
      const e = 1 - Math.pow(1 - p, 3)
      setN(Math.round(a + (value - a) * e))
      if (p < 1) raf = requestAnimationFrame(tick)
      else from.current = value
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, duration])
  return <>{n.toLocaleString()}</>
}

export function CopyButton({ text, label = 'Copy', size = 'sm' }) {
  const [done, setDone] = useState(false)
  const toast = useToast()
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select()
      try { document.execCommand('copy') } catch { /* ignore */ }
      ta.remove()
    }
    setDone(true); toast('Copied to clipboard', 'success', 1800)
    setTimeout(() => setDone(false), 1500)
  }
  return <Button size={size} icon={done ? Check : Copy} onClick={copy} aria-label={`${label} to clipboard`}>{label}</Button>
}

const RECORD_STATUS = {
  Completed: ['b-green', 'Completed'], 'Requires Review': ['b-amber', 'Requires Review'], Failed: ['b-red', 'Failed'],
  Uploading: ['b-cyan b-processing', 'Uploading'], Securing: ['b-cyan b-processing', 'Securing'], Hashing: ['b-cyan b-processing', 'Hashing'],
  Extracting: ['b-cyan b-processing', 'Extracting'], Analyzing: ['b-cyan b-processing', 'Analyzing'],
}
const CASE_STATUS = {
  active: ['b-blue', 'Active'], processing: ['b-cyan b-processing', 'Processing'], requires_review: ['b-amber', 'Requires Review'],
  completed: ['b-green', 'Completed'], archived: ['b-neutral', 'Archived'],
}
const CONFLICT_STATUS = {
  requires_review: ['b-amber', 'Requires Review'], reviewed: ['b-blue', 'Reviewed'], accepted: ['b-green', 'Accepted'],
  resolved: ['b-green', 'Resolved'], escalated: ['b-red', 'Escalated'],
}
export function StatusBadge({ status, kind = 'record' }) {
  const map = kind === 'case' ? CASE_STATUS : kind === 'conflict' ? CONFLICT_STATUS : RECORD_STATUS
  const [cls, label] = map[status] || ['b-neutral', status]
  return <span className={`badge ${cls}`}><span className="dot" />{label}</span>
}

export const RoleBadge = ({ role, label }) => <span className={`role-badge role-${role}`}>{label || role}</span>
export const Synthetic = () => <span className="synthetic" title="All demo people, organisations and identifiers are fictional">Synthetic Demo Data</span>

export function FileIcon({ ext, size = 40 }) {
  const e = (ext || '').toUpperCase().replace('.', '')
  const c = { PDF: ['#fb7185', 'rgba(244,63,94,.14)'], DOCX: ['#c8b6a6', 'rgba(168,151,138,.14)'], TXT: ['#b3a89f', 'rgba(148,163,184,.14)'],
    PNG: ['#34d399', 'rgba(16,185,129,.14)'], JPG: ['#fbbf24', 'rgba(245,158,11,.14)'], JPEG: ['#fbbf24', 'rgba(245,158,11,.14)'] }[e] || ['#e8a86b', 'rgba(217,119,69,.14)']
  return <div className="file-ic" style={{ color: c[0], background: c[1], width: size, height: size }} aria-hidden>{e || 'FILE'}</div>
}

export function Pagination({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (pages <= 1) return null
  return (
    <div className="row between" style={{ padding: '12px 16px' }}>
      <span className="small faint">Page {page} of {pages} · {total} items</span>
      <div className="row">
        <Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <Button size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </div>
  )
}

export function Principle({ children }) {
  return (
    <div className="principle" role="note">
      <UserCheck aria-hidden />
      <span>{children || <><b>We surface evidence signals. Humans make the final determination.</b> Nothing here declares a record genuine or fake.</>}</span>
    </div>
  )
}

export function BrandFlow({ className = '' }) {
  const steps = [['Scattered', Shuffle], ['Extract', ScanSearch], ['Connect', Link2], ['Analyze', Network], ['Review', UserCheck]]
  return (
    <div className={`flow ${className}`} aria-label="Scattered, extract, connect, analyze, review">
      {steps.map(([s, I], i) => (
        <div key={s} className="row" style={{ gap: 0 }}>
          <div className="flow-step" style={{ '--i': i }}><I aria-hidden />{s}</div>
          {i < steps.length - 1 && <div className="flow-arrow" style={{ '--i': i }} aria-hidden />}
        </div>
      ))}
    </div>
  )
}

export function Logo({ size = 38 }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <defs>
        <linearGradient id="lg1" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#d97745" /><stop offset="1" stopColor="#e8c39e" /></linearGradient>
      </defs>
      <rect width="64" height="64" rx="18" fill="url(#lg1)" opacity=".16" />
      <rect x=".75" y=".75" width="62.5" height="62.5" rx="17.5" fill="none" stroke="url(#lg1)" strokeOpacity=".55" strokeWidth="1.5" />
      <path d="M21 15h15l8 8v26H21z" fill="none" stroke="url(#lg1)" strokeWidth="3.2" strokeLinejoin="round" />
      <path d="M36 15v8h8" fill="none" stroke="url(#lg1)" strokeWidth="3.2" strokeLinejoin="round" />
      <circle cx="27" cy="31" r="3.2" fill="#e8c39e"><animate attributeName="r" values="3.2;4;3.2" dur="2.4s" repeatCount="indefinite" /></circle>
      <circle cx="38" cy="37" r="3.2" fill="#e8a86b" />
      <circle cx="30" cy="42.5" r="2.6" fill="#f472b6" />
      <path d="M27 31l11 6-8 5.5z" fill="none" stroke="#f0c9a4" strokeWidth="1.4" />
    </svg>
  )
}

export function PageHead({ eyebrow, title, lead, actions, icon: Icon }) {
  return (
    <div className="page-head">
      <div>
        {eyebrow && <div className="eyebrow">{Icon && <Icon size={14} />}{eyebrow}</div>}
        <h1>{title}</h1>
        {lead && <p className="lead">{lead}</p>}
      </div>
      {actions && <div className="row wrap">{actions}</div>}
    </div>
  )
}

export const ArrowLink = ({ children }) => <span className="row" style={{ gap: 4 }}>{children}<ArrowRight size={14} /></span>
