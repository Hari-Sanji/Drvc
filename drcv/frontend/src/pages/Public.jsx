import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  ArrowRight, CalendarRange, Eye, EyeOff, FileStack, Fingerprint, KeyRound, LogIn, Mail, Network, Rocket, ScanSearch,
  ShieldCheck, Smartphone, Sparkles, UserCheck,
} from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import { ThemeToggle } from '../components/Layout'
import TryIt from '../components/TryIt'
import { useDemo } from '../demo'
import { BrandFlow, Button, Logo, Principle, RoleBadge, useToast } from '../ui'

const PILLARS = [
  ['Integrity', Fingerprint, 'ic-cyan', 'SHA-256 content fingerprints for every record, re-verifiable at any time.'],
  ['Context', ScanSearch, 'ic-violet', 'Metadata, text layers and OCR extracted — and what is not available is shown too.'],
  ['Chronology', CalendarRange, 'ic-amber', 'Dates and events reconstructed into one interactive timeline.'],
  ['Relationships', Network, 'ic-pink', 'Shared people, places, identifiers and content connected across records.'],
]

export function Landing() {
  const { user, login } = useAuth()
  const demo = useDemo()
  const navigate = useNavigate()
  const toast = useToast()
  const [busy, setBusy] = useState(false)

  const launch = async () => {
    setBusy(true)
    try {
      if (!user) {
        const d = await login('admin@demo.local', 'Admin@123', false)
        if (d?.requires_2fa) { toast('The demo admin account has two-factor authentication on. Sign in with the code.', 'info'); navigate('/login'); return }
      }
      await demo.launch()
    } catch (e) {
      toast(e.status === 401 ? 'The demo admin account is not available. Sign in with another account.' : e.message, 'error')
      navigate('/login')
    } finally { setBusy(false) }
  }
  return (
    <div className="landing">
      <nav className="land-nav" aria-label="Site">
        <Link to="/" className="row" style={{ textDecoration: 'none', color: 'inherit', gap: 11 }}>
          <Logo /><div><div className="brand-name gradient-text">DRCV</div><div className="brand-sub hide-sm">Digital Record Context Verification</div></div>
        </Link>
        <div className="row">
          <ThemeToggle />
          <Button variant="ghost" onClick={() => navigate(user ? '/app/dashboard' : '/login')}>{user ? 'Open platform' : 'Sign in'}</Button>
        </div>
      </nav>
      <section className="hero">
        <div className="kicker"><Sparkles size={14} color="var(--violet-2)" /><b>Evidence signals</b> — not verdicts. Humans make the final determination.</div>
        <h1>Digital Record<br /><span className="gradient-text">Context Verification</span></h1>
        <p className="tagline">Establishing the Context, Integrity, Chronology &amp; Relationships of Digital Records</p>
        <p className="support">Bring fragmented digital records together, extract meaningful information, discover relationships, reconstruct chronology, and surface potential inconsistencies for human review.</p>
        <div className="cta">
          <Button variant="primary" size="lg" icon={Rocket} loading={busy} onClick={launch}>Launch Demo</Button>
          <Button size="lg" iconRight={ArrowRight} onClick={() => navigate(user ? '/app/dashboard' : '/login')}>Explore Platform</Button>
        </div>
        <BrandFlow className="hero-flow" />
      </section>
      <TryIt onLaunchDemo={launch} />
      <section className="pillars" aria-label="Four pillars">
        {PILLARS.map(([t, I, c, d], i) => (
          <div key={t} className="card pillar hover" style={{ animation: `page-in .6s ${200 + i * 110}ms both` }}>
            <div className={`pi ${c}`}><I /></div>
            <h3>{t}</h3>
            <p className="small muted">{d}</p>
          </div>
        ))}
      </section>
      <section className="io" aria-label="How it works">
        <div className="card">
          <h4>Input</h4>
          <h3 className="display" style={{ fontSize: 20 }}>Multiple digital records</h3>
          <p className="small muted" style={{ marginTop: 8 }}>PDFs, scans, images, DOCX and text files — certificates, statements, invoices, IDs and supporting documents from one case.</p>
          <div className="row wrap" style={{ marginTop: 14 }}>{['PDF', 'JPG', 'PNG', 'DOCX', 'TXT'].map((x) => <span key={x} className="badge b-neutral">{x}</span>)}</div>
        </div>
        <div className="card glow-border">
          <h4>Process</h4>
          <h3 className="display" style={{ fontSize: 20 }}>Hash · Metadata · OCR · NLP · Relationship analysis</h3>
          <div className="stack small muted" style={{ marginTop: 12, gap: 8 }}>
            {[[ShieldCheck, 'Validate file signature and store securely'], [Fingerprint, 'Generate a real SHA-256 fingerprint'], [ScanSearch, 'Extract metadata, text and OCR with confidence'],
              [FileStack, 'Detect people, organisations, IDs, dates, amounts, events'], [Network, 'TF-IDF similarity + entity matching to connect records']].map(([I, t]) => (
              <div key={t} className="row"><I size={16} color="var(--cyan-2)" />{t}</div>
            ))}
          </div>
        </div>
        <div className="card">
          <h4>Output</h4>
          <h3 className="display" style={{ fontSize: 20 }}>Timeline · Relationship map · Conflict alerts · Report</h3>
          <p className="small muted" style={{ marginTop: 8 }}>Potential inconsistencies are routed to a reviewer who resolves, accepts or escalates them — every action lands in the audit trail.</p>
          <div className="row" style={{ marginTop: 14 }}><UserCheck size={16} color="var(--amber-2)" /><span className="small">Final determination: human reviewer</span></div>
        </div>
      </section>
    </div>
  )
}

export function Login() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const loc = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [remember, setRemember] = useState(true)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [accounts, setAccounts] = useState([])
  const [needCode, setNeedCode] = useState(false)
  const [code, setCode] = useState('')
  const dest = loc.state?.from || '/app/dashboard'

  useEffect(() => { if (user) navigate(dest, { replace: true }) }, [user, navigate, dest])
  useEffect(() => { api.get('/auth/demo-accounts').then(setAccounts).catch(() => setAccounts([])) }, [])

  const submit = async (e, creds) => {
    e?.preventDefault()
    const em = creds?.email ?? email
    const pw = creds?.password ?? password
    if (!em || !pw) { setErr('Please enter your email and password.'); return }
    if (needCode && !creds && code.replace(/\D/g, '').length !== 6) { setErr('Enter the 6-digit code from your authenticator app.'); return }
    setBusy(true); setErr('')
    try {
      const d = await login(em, pw, remember, needCode && !creds ? code : undefined)
      if (d?.requires_2fa) { setEmail(em); setPassword(pw); setNeedCode(true); setCode('') }
    } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }
  return (
    <div className="login-shell">
      <section className="login-art">
        <Link to="/" className="row" style={{ textDecoration: 'none', color: 'inherit', gap: 12 }}>
          <Logo size={44} /><div><div className="brand-name gradient-text" style={{ fontSize: 22 }}>DRCV</div><div className="brand-sub">Digital Record Context Verification</div></div>
        </Link>
        <div>
          <h1 style={{ fontSize: 44, lineHeight: 1.05, letterSpacing: '-0.025em' }}>From <span className="gradient-text">scattered records</span><br />to reviewable evidence signals.</h1>
          <p className="muted" style={{ marginTop: 16, maxWidth: 520, fontSize: 15 }}>Establishing the Context, Integrity, Chronology &amp; Relationships of Digital Records.</p>
          <div style={{ marginTop: 28 }}><BrandFlow /></div>
        </div>
        <Principle />
      </section>
      <section className="login-panel">
        <div className="card login-card glow-border">
          <div className="row" style={{ gap: 12, marginBottom: 20 }}>
            <Logo size={40} />
            <div><h2>Sign in</h2><p className="small muted">Digital Record Context Verification</p></div>
            <div className="grow" /><ThemeToggle />
          </div>
          <form className="stack" onSubmit={submit} noValidate>
            <div className="field">
              <label htmlFor="email">Email</label>
              <div className="input-icon"><Mail /><input id="email" className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@organisation.org" required /></div>
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <div className="input-icon" style={{ position: 'relative' }}>
                <KeyRound />
                <input id="password" className="input" type={show ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} style={{ paddingRight: 44 }} required />
                <button type="button" className="btn ghost icon sm" style={{ position: 'absolute', right: 4, top: 4 }} onClick={() => setShow((s) => !s)} aria-label={show ? 'Hide password' : 'Show password'}>{show ? <EyeOff /> : <Eye />}</button>
              </div>
            </div>
            <div className="row between">
              <label className="checkbox"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />Remember me</label>
              <span className="tiny faint">Sessions are signed JWTs</span>
            </div>
            {needCode && (
              <div className="field" style={{ animation: 'page-in .3s ease both' }}>
                <label htmlFor="otp">Authentication code</label>
                <div className="input-icon"><Smartphone /><input id="otp" className="input" inputMode="numeric" autoComplete="one-time-code" autoFocus
                  maxLength={7} placeholder="6-digit code" value={code} onChange={(e) => setCode(e.target.value.replace(/[^0-9 ]/g, ''))} style={{ letterSpacing: '.3em' }} /></div>
                <span className="tiny faint">Two-factor authentication is on for this account. Open your authenticator app.</span>
              </div>
            )}
            {err && <div className="form-error" role="alert">{err}</div>}
            <Button type="submit" variant="primary" size="lg" icon={needCode ? ShieldCheck : LogIn} loading={busy}>{needCode ? 'Verify & sign in' : 'Sign in'}</Button>
            {needCode && <Button variant="ghost" size="sm" onClick={() => { setNeedCode(false); setCode(''); setErr('') }}>Use a different account</Button>}
          </form>
          {accounts.length > 0 && (
            <div style={{ marginTop: 24 }}>
              <div className="row between" style={{ marginBottom: 10 }}>
                <h3 className="row"><Sparkles size={16} color="var(--violet-2)" />Try Demo Accounts</h3>
                <span className="synthetic">Synthetic</span>
              </div>
              <div className="demo-acc">
                {accounts.map((a) => (
                  <button key={a.email} type="button" onClick={() => { setEmail(a.email); setPassword(a.password); submit(null, a) }} disabled={busy} title={a.summary}>
                    <div className="da-role"><RoleBadge role={a.role} label={a.role_label} /></div>
                    <div className="da-mail">{a.email}</div>
                    <div className="tiny muted" style={{ marginTop: 4, lineHeight: 1.35 }}>{a.summary}</div>
                  </button>
                ))}
              </div>
              <p className="tiny faint" style={{ marginTop: 10 }}>Each role has different permissions enforced by the API — try the Viewer to see read-only access.</p>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
