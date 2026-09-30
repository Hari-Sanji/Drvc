import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  AlertOctagon, Bell, BookOpenCheck, CalendarClock, ClipboardCheck, FileStack, FileText, FolderKanban, Hash,
  LayoutDashboard, LogOut, Menu, Moon, Network, Rocket, ScrollText, Search, Settings, Sun, UserCog, Users,
} from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import { useDemo } from '../demo'
import { Button, Logo, RoleBadge, timeAgo, useDebounced, useInterval } from '../ui'

export function useTheme() {
  const [theme, setTheme] = useState(() => document.documentElement.getAttribute('data-theme') || 'dark')
  const toggle = () => {
    const t = theme === 'dark' ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', t)
    try { localStorage.setItem('drcv-theme', t) } catch { /* ignore */ }
    setTheme(t)
  }
  return [theme, toggle]
}

export function ThemeToggle() {
  const [theme, toggle] = useTheme()
  return (
    <button className="btn ghost icon" onClick={toggle} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} data-tip={theme === 'dark' ? 'Light theme' : 'Dark theme'}>
      {theme === 'dark' ? <Sun /> : <Moon />}
    </button>
  )
}

function GlobalSearch() {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [res, setRes] = useState(null)
  const [loading, setLoading] = useState(false)
  const dq = useDebounced(q, 280)
  const navigate = useNavigate()
  const box = useRef(null)
  const input = useRef(null)

  useEffect(() => {
    const onKey = (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); input.current?.focus() } }
    const onDoc = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false) }
    document.addEventListener('keydown', onKey); document.addEventListener('mousedown', onDoc)
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('mousedown', onDoc) }
  }, [])
  useEffect(() => {
    if (dq.trim().length < 2) { setRes(null); return }
    const ctl = new AbortController()
    setLoading(true)
    api.get(`/search?q=${encodeURIComponent(dq.trim())}&limit=5`, { signal: ctl.signal })
      .then(setRes).catch(() => {}).finally(() => setLoading(false))
    return () => ctl.abort()
  }, [dq])

  const go = (to) => { setOpen(false); setQ(''); navigate(to) }
  const total = res ? res.cases.length + res.records.length + res.entities.length + res.events.length : 0
  return (
    <div className="search-box" ref={box}>
      <div className="input-icon">
        <Search aria-hidden />
        <input ref={input} className="input" placeholder="Search cases, records, names, IDs, places, events…" value={q}
          aria-label="Global search" onFocus={() => setOpen(true)} onChange={(e) => { setQ(e.target.value); setOpen(true) }}
          onKeyDown={(e) => { if (e.key === 'Enter' && q.trim()) go(`/app/search?q=${encodeURIComponent(q.trim())}`); if (e.key === 'Escape') setOpen(false) }} />
      </div>
      <kbd>Ctrl K</kbd>
      {open && q.trim().length >= 2 && (
        <div className="dropdown search-results">
          {loading && !res && <div className="sr-group row muted small" style={{ padding: 16 }}><span className="spinner" />Searching…</div>}
          {res && total === 0 && <div className="sr-group muted small" style={{ padding: 16 }}>No matches for “{q}”.</div>}
          {res?.cases.length > 0 && <div className="sr-group"><h4>Cases</h4>{res.cases.map((c) => (
            <a key={c.id} className="sr-item" onClick={() => go(`/app/cases/${c.id}`)}><FolderKanban /><span className="grow truncate">{c.name}</span><span className="tiny faint">{c.code}</span></a>))}</div>}
          {res?.records.length > 0 && <div className="sr-group"><h4>Records</h4>{res.records.map((r) => (
            <a key={r.id} className="sr-item" onClick={() => go(`/app/records/${r.id}`)}><FileText /><span className="grow truncate">{r.filename}</span><span className="tiny faint">{r.doc_type}</span></a>))}</div>}
          {res?.entities.length > 0 && <div className="sr-group"><h4>People, IDs, places & organizations</h4>{res.entities.slice(0, 6).map((e, i) => (
            <a key={i} className="sr-item" onClick={() => go(`/app/records/${e.record_ids[0]}#extracted`)}><Hash /><span className="grow truncate">{e.value}</span><span className="tiny faint">{e.type} · {e.record_ids.length} record{e.record_ids.length > 1 ? 's' : ''}</span></a>))}</div>}
          {res?.events.length > 0 && <div className="sr-group"><h4>Events</h4>{res.events.map((e) => (
            <a key={e.id} className="sr-item" onClick={() => go(`/app/cases/${e.case_id}/timeline`)}><CalendarClock /><span className="grow truncate">{e.label}</span><span className="tiny faint">{e.date_label}</span></a>))}</div>}
          <div className="sr-group" style={{ borderTop: '1px solid var(--border)' }}>
            <a className="sr-item" onClick={() => go(`/app/search?q=${encodeURIComponent(q.trim())}`)}><Search /><span className="grow">Advanced search with filters for “{q}”</span></a>
          </div>
        </div>
      )}
    </div>
  )
}

const NOTIF_COLORS = { conflict: 'var(--red)', review: 'var(--green)', report: 'var(--violet)', analysis: 'var(--cyan)', case: 'var(--blue)' }

function Notifications() {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState({ items: [], unread: 0 })
  const ref = useRef(null)
  const navigate = useNavigate()
  const load = () => api.get('/notifications').then(setData).catch(() => {})
  useEffect(() => { load() }, [])
  useInterval(load, 20000)
  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])
  const toggle = () => {
    const o = !open
    setOpen(o)
    if (o && data.unread) api.post('/notifications/seen').then(() => setTimeout(load, 1500)).catch(() => {})
  }
  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <button className="btn ghost icon" onClick={toggle} aria-label={`Notifications${data.unread ? `, ${data.unread} unread` : ''}`} aria-expanded={open}>
        <Bell />{data.unread > 0 && <span className="bell-badge">{data.unread > 9 ? '9+' : data.unread}</span>}
      </button>
      {open && (
        <div className="dropdown notif-panel">
          <div className="card-head"><h3><Bell />Notifications</h3><span className="tiny faint">Latest activity</span></div>
          <div style={{ maxHeight: 420, overflowY: 'auto' }}>
            {data.items.length === 0 && <p className="muted small" style={{ padding: 18 }}>You're all caught up.</p>}
            {data.items.map((n) => (
              <div key={n.id} className="notif-item" onClick={() => { setOpen(false); if (n.record_id) navigate(`/app/records/${n.record_id}`); else if (n.case_id) navigate(`/app/cases/${n.case_id}${n.category === 'conflict' ? '/conflicts' : ''}`) }}>
                <span className="ndot" style={{ background: n.result === 'failed' ? 'var(--red)' : NOTIF_COLORS[n.category] || 'var(--text-3)', opacity: n.unread ? 1 : 0.35 }} />
                <div className="grow">
                  <div className="small" style={{ fontWeight: n.unread ? 600 : 500 }}>{n.action}</div>
                  <div className="tiny faint truncate">{n.target ? `${n.target} · ` : ''}{n.user} · {timeAgo(n.ts)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function Layout() {
  const { user, can, logout } = useAuth()
  const demo = useDemo()
  const navigate = useNavigate()
  const [menu, setMenu] = useState(false)
  const [counts, setCounts] = useState({ unresolved: 0 })
  const loc = useLocation()
  useEffect(() => { setMenu(false) }, [loc.pathname])
  const loadCounts = () => api.get('/conflicts?status=unresolved&page_size=1').then((d) => setCounts({ unresolved: d.total })).catch(() => {})
  useEffect(() => { loadCounts() }, [loc.pathname])
  useEffect(() => { window.scrollTo({ top: 0 }) }, [loc.pathname])

  const nav = [
    ['Workspace', [
      ['/app/dashboard', 'Dashboard', LayoutDashboard, true],
      ['/app/cases', 'Cases', FolderKanban, can('case:view')],
      ['/app/records', 'Records', FileStack, can('record:view')],
      ['/app/timeline', 'Timeline', CalendarClock, can('analysis:view')],
      ['/app/graph', 'Relationship Graph', Network, can('analysis:view')],
      ['/app/conflicts', 'Conflict Center', AlertOctagon, can('analysis:view'), counts.unresolved],
      ['/app/review', 'Review Center', ClipboardCheck, can('analysis:view')],
      ['/app/reports', 'Reports', BookOpenCheck, can('report:view')],
    ]],
    ['Governance', [
      ['/app/audit', 'Audit Logs', ScrollText, can('audit:view')],
      ['/app/users', 'User Management', Users, can('user:manage')],
      ['/app/settings', 'Settings', can('settings:manage') ? UserCog : Settings, true],
    ]],
  ]
  const initials = user?.name?.split(' ').map((x) => x[0]).slice(0, 2).join('') || '?'
  return (
    <div className="app">
      {menu && <div className="sidebar-scrim" onClick={() => setMenu(false)} />}
      <aside className={`sidebar ${menu ? 'open' : ''}`} aria-label="Main navigation">
        <Link to="/app/dashboard" className="brand" style={{ textDecoration: 'none', color: 'inherit' }}>
          <Logo />
          <div><div className="brand-name gradient-text">DRCV</div><div className="brand-sub">Digital Record Context<br />Verification</div></div>
        </Link>
        <Button variant="primary" icon={Rocket} onClick={demo.launch} style={{ margin: '0 4px 6px' }}>Launch Demo</Button>
        <nav className="nav">
          {nav.map(([label, items]) => (
            <div key={label}>
              <div className="nav-label">{label}</div>
              {items.filter((x) => x[3]).map(([to, text, Icon, , count]) => (
                <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'active' : '')}>
                  <Icon aria-hidden />{text}{count > 0 && <span className="nav-count" aria-label={`${count} unresolved`}>{count}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="user-chip">
            <div className="avatar" aria-hidden>{initials}</div>
            <div className="who"><b>{user?.name}</b><RoleBadge role={user?.role} label={user?.role_label} /></div>
            <button className="btn ghost icon sm" onClick={async () => { await logout(); navigate('/login', { replace: true, state: null }) }} aria-label="Sign out" data-tip="Sign out"><LogOut /></button>
          </div>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <button className="btn ghost icon menu-btn" onClick={() => setMenu(true)} aria-label="Open navigation"><Menu /></button>
          <GlobalSearch />
          {!demo.open && demo.caseId && <Button size="sm" className="hide-sm" icon={Rocket} onClick={() => demo.setGuide({ open: true, min: false })}>Demo guide</Button>}
          <Notifications />
          <ThemeToggle />
        </header>
        <main className="content" id="main">
          <div className="page" key={loc.pathname.split('/').slice(0, 4).join('/')}><Outlet context={{ refreshCounts: loadCounts }} /></div>
        </main>
      </div>
    </div>
  )
}
