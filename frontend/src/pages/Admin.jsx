import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Check, Cpu, Database, KeyRound, Minus, Palette, RefreshCw, Save, Settings as SettingsIcon, ShieldCheck, SlidersHorizontal, Smartphone, UserPlus, Users as UsersIcon,
} from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import { useTheme } from '../components/Layout'
import { useDemo } from '../demo'
import { Button, Confirm, CopyButton, ErrorState, Loading, Modal, PageHead, RoleBadge, fmtDateTime, useAsync, useToast } from '../ui'

const ROLES = [['admin', 'Admin'], ['investigator', 'Investigator'], ['reviewer', 'Reviewer'], ['viewer', 'Viewer']]

function UserModal({ onClose, onSaved }) {
  const toast = useToast()
  const [f, setF] = useState({ name: '', email: '', role: 'viewer', password: '' })
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true); setErr('')
    try { await api.post('/users', f); toast('User created', 'success'); onSaved(); onClose() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <Modal title="Create user" icon={UserPlus} onClose={onClose} footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>Create user</Button></>}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save() }}>
        <div className="field"><label htmlFor="un">Full name</label><input id="un" className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
        <div className="field"><label htmlFor="ue">Email</label><input id="ue" type="email" className="input" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
        <div className="field"><label htmlFor="ur">Role</label><select id="ur" className="select" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
        <div className="field"><label htmlFor="up">Initial password</label><input id="up" type="password" className="input" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          <span className="tiny faint">At least 8 characters with upper and lower case letters and a number.</span></div>
        {err && <div className="form-error" role="alert">{err}</div>}
      </form>
    </Modal>
  )
}

function PasswordModal({ user, onClose }) {
  const toast = useToast()
  const [pw, setPw] = useState(''); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true); setErr('')
    try { await api.post(`/users/${user.id}/password`, { password: pw }); toast(`Password reset for ${user.email}`, 'success'); onClose() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <Modal title={`Reset password — ${user.name}`} icon={KeyRound} onClose={onClose} footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>Reset password</Button></>}>
      <div className="field"><label htmlFor="np">New password</label><input id="np" type="password" className="input" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></div>
      {err && <div className="form-error" role="alert" style={{ marginTop: 10 }}>{err}</div>}
    </Modal>
  )
}

export function Users() {
  const { user: me } = useAuth()
  const toast = useToast()
  const users = useAsync(() => api.get('/users'), [])
  const roles = useAsync(() => api.get('/auth/roles'), [])
  const [modal, setModal] = useState(null)
  const patch = async (u, body, msg) => { try { await api.patch(`/users/${u.id}`, body); toast(msg, 'success'); users.reload(true) } catch (e) { toast(e.message, 'error') } }
  if (users.error) return <ErrorState error={users.error} onRetry={users.reload} />
  return (
    <>
      <PageHead eyebrow="Governance" icon={UsersIcon} title="User Management" lead="Accounts, roles and access. Permissions are enforced by the API on every request — the interface only mirrors them."
        actions={<Button variant="primary" icon={UserPlus} onClick={() => setModal({ t: 'new' })}>Create user</Button>} />
      <div className="card" style={{ marginBottom: 18 }}>
        {!users.data ? <Loading /> : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>User</th><th>Role</th><th>Status</th><th className="hide-sm">Last sign-in</th><th /></tr></thead>
            <tbody>{users.data.map((u) => (
              <tr key={u.id}>
                <td><div className="row"><div className="avatar" style={{ width: 30, height: 30, fontSize: 11 }} aria-hidden>{u.name.split(' ').map((x) => x[0]).slice(0, 2).join('')}</div><div><b className="small">{u.name}</b>{u.is_demo && <span className="tiny faint"> · demo</span>}<div className="tiny faint">{u.email}</div></div></div></td>
                <td>{u.id === me.id ? <RoleBadge role={u.role} label={u.role_label} /> : (
                  <select className="select" style={{ height: 32, width: 150 }} aria-label={`Role for ${u.name}`} value={u.role} onChange={(e) => patch(u, { role: e.target.value }, `${u.name} is now ${e.target.selectedOptions[0].text}`)}>
                    {ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>)}</td>
                <td><div className="row wrap" style={{ gap: 6 }}><span className={`badge ${u.is_active ? 'b-green' : 'b-neutral'}`}><span className="dot" />{u.is_active ? 'Active' : 'Disabled'}</span>
                  {u.totp_enabled && <span className="badge b-cyan" title="Two-factor authentication on"><Smartphone />2FA</span>}</div></td>
                <td className="small muted hide-sm">{fmtDateTime(u.last_login)}</td>
                <td><div className="row" style={{ justifyContent: 'flex-end' }}>
                  <Button size="sm" icon={KeyRound} onClick={() => setModal({ t: 'pw', u })}>Reset password</Button>
                  {u.totp_enabled && <Button size="sm" icon={Smartphone} onClick={async () => { try { await api.post(`/users/${u.id}/reset-2fa`); toast(`2FA reset for ${u.name}`, 'success'); users.reload(true) } catch (e) { toast(e.message, 'error') } }}>Reset 2FA</Button>}
                  {u.id !== me.id && <Button size="sm" variant={u.is_active ? 'danger' : 'success'} onClick={() => setModal({ t: 'toggle', u })}>{u.is_active ? 'Disable' : 'Enable'}</Button>}
                </div></td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
      {roles.data && (
        <div className="card">
          <div className="card-head"><h3><ShieldCheck />Role permissions matrix</h3><span className="tiny faint">Enforced server-side</span></div>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Permission</th>{roles.data.roles.map((r) => <th key={r.key} style={{ textAlign: 'center' }}><RoleBadge role={r.key} label={r.label} /></th>)}</tr></thead>
            <tbody>{Object.entries(roles.data.permission_labels).map(([p, l]) => (
              <tr key={p}><td className="small">{l}</td>{roles.data.roles.map((r) => (
                <td key={r.key} style={{ textAlign: 'center' }}>{r.permissions.includes(p) ? <Check size={16} color="var(--green-2)" aria-label="Allowed" /> : <Minus size={16} color="var(--text-3)" aria-label="Not allowed" />}</td>))}</tr>
            ))}</tbody>
          </table></div>
        </div>
      )}
      {modal?.t === 'new' && <UserModal onClose={() => setModal(null)} onSaved={() => users.reload(true)} />}
      {modal?.t === 'pw' && <PasswordModal user={modal.u} onClose={() => setModal(null)} />}
      {modal?.t === 'toggle' && <Confirm danger={modal.u.is_active} title={`${modal.u.is_active ? 'Disable' : 'Enable'} ${modal.u.name}?`}
        message={modal.u.is_active ? 'The user will no longer be able to sign in. Their audit history is preserved.' : 'The user will be able to sign in again.'}
        confirmLabel={modal.u.is_active ? 'Disable user' : 'Enable user'} onClose={() => setModal(null)}
        onConfirm={async () => { await patch(modal.u, { is_active: !modal.u.is_active }, `User ${modal.u.is_active ? 'disabled' : 'enabled'}`); setModal(null) }} />}
    </>
  )
}

function SecurityCard() {
  const { user, applySession, refreshMe } = useAuth()
  const toast = useToast()
  const [pw, setPw] = useState({ current: '', next: '', confirm: '' })
  const [pwErr, setPwErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [setup, setSetup] = useState(null)
  const [code, setCode] = useState('')
  const [off, setOff] = useState(null)
  const [tfaErr, setTfaErr] = useState('')

  const changePw = async () => {
    setPwErr('')
    if (pw.next !== pw.confirm) { setPwErr('The new passwords do not match.'); return }
    setBusy(true)
    try {
      const d = await api.post('/auth/change-password', { current_password: pw.current, new_password: pw.next })
      applySession(d)
      setPw({ current: '', next: '', confirm: '' })
      toast('Password changed. Other sessions have been signed out.', 'success')
    } catch (e) { setPwErr(e.message) } finally { setBusy(false) }
  }
  const startSetup = async () => {
    setTfaErr('')
    try { setSetup(await api.post('/auth/2fa/setup')); setCode('') } catch (e) { toast(e.message, 'error') }
  }
  const enable = async () => {
    setTfaErr('')
    try { await api.post('/auth/2fa/enable', { code }); await refreshMe(); setSetup(null); toast('Two-factor authentication is on', 'success') } catch (e) { setTfaErr(e.message) }
  }
  const disable = async () => {
    setTfaErr('')
    try { await api.post('/auth/2fa/disable', off); await refreshMe(); setOff(null); toast('Two-factor authentication turned off', 'info') } catch (e) { setTfaErr(e.message) }
  }
  return (
    <div className="card span2">
      <div className="card-head"><h3><KeyRound />Security</h3>
        <span className={`badge ${user.totp_enabled ? 'b-green' : 'b-neutral'}`}><Smartphone />2FA {user.totp_enabled ? 'on' : 'off'}</span></div>
      <div className="card-body grid g2">
        <form className="stack" onSubmit={(e) => { e.preventDefault(); changePw() }}>
          <b className="small">Change password</b>
          <div className="field"><label htmlFor="cpw">Current password</label><input id="cpw" type="password" className="input" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} /></div>
          <div className="field"><label htmlFor="npw">New password</label><input id="npw" type="password" className="input" autoComplete="new-password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} /></div>
          <div className="field"><label htmlFor="npw2">Confirm new password</label><input id="npw2" type="password" className="input" autoComplete="new-password" value={pw.confirm} onChange={(e) => setPw({ ...pw, confirm: e.target.value })} /></div>
          <span className="tiny faint">At least 8 characters with upper and lower case letters and a number. Changing it signs out your other sessions.</span>
          {pwErr && <div className="form-error" role="alert">{pwErr}</div>}
          <div><Button type="submit" variant="primary" icon={Save} loading={busy} disabled={!pw.current || !pw.next}>Update password</Button></div>
        </form>
        <div className="stack">
          <b className="small">Two-factor authentication (authenticator app)</b>
          <p className="small muted">Adds a 6-digit code from Google Authenticator, Microsoft Authenticator or a similar app at sign-in.</p>
          {!user.totp_enabled && !setup && <div><Button icon={Smartphone} onClick={startSetup}>Set up two-factor authentication</Button></div>}
          {setup && (
            <div className="stack" style={{ animation: 'page-in .3s ease both' }}>
              <span className="small">1. Scan this QR code with your authenticator app:</span>
              {setup.qr_svg ? <div className="qr-box" dangerouslySetInnerHTML={{ __html: setup.qr_svg }} aria-label="QR code for authenticator setup" /> : null}
              <span className="tiny faint">Can't scan? Enter this key manually:</span>
              <div className="row"><code className="mono small" style={{ wordBreak: 'break-all' }}>{setup.secret.match(/.{1,4}/g).join(' ')}</code><CopyButton text={setup.secret} label="Copy" /></div>
              <span className="small">2. Enter the 6-digit code the app shows:</span>
              <div className="row"><input className="input" style={{ width: 150, letterSpacing: '.3em' }} inputMode="numeric" maxLength={7} aria-label="Authenticator code" value={code} onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, ''))} />
                <Button variant="primary" onClick={enable} disabled={code.length !== 6}>Turn on</Button><Button variant="ghost" onClick={() => setSetup(null)}>Cancel</Button></div>
            </div>
          )}
          {user.totp_enabled && !off && <div><Button variant="danger" onClick={() => setOff({ password: '', code: '' })}>Turn off two-factor authentication</Button></div>}
          {off && (
            <div className="stack">
              <input type="password" className="input" placeholder="Your password" aria-label="Password" value={off.password} onChange={(e) => setOff({ ...off, password: e.target.value })} />
              <input className="input" placeholder="Current 6-digit code" aria-label="Authenticator code" inputMode="numeric" maxLength={7} value={off.code} onChange={(e) => setOff({ ...off, code: e.target.value.replace(/[^0-9]/g, '') })} />
              <div className="row"><Button variant="danger" onClick={disable}>Confirm turn off</Button><Button variant="ghost" onClick={() => setOff(null)}>Cancel</Button></div>
            </div>
          )}
          {tfaErr && <div className="form-error" role="alert">{tfaErr}</div>}
          {user.is_demo && <p className="tiny faint">This is a shared demo account. An admin's "Reset demo" restores its published password and turns 2FA off.</p>}
        </div>
      </div>
    </div>
  )
}

export function Settings() {
  const { user, permissions } = useAuth()
  const toast = useToast()
  const demo = useDemo()
  const [theme, toggleTheme] = useTheme()
  const { data, error, reload } = useAsync(() => api.get('/settings'), [])
  const [f, setF] = useState(null)
  const [busy, setBusy] = useState(false)
  const [reset, setReset] = useState(false)
  useEffect(() => { if (data) setF(data.settings) }, [data])
  if (error) return <ErrorState error={error} onRetry={reload} />
  if (!data || !f) return <Loading />
  const ed = data.editable
  const save = async () => {
    setBusy(true)
    try { await api.put('/settings', f); toast('Settings saved', 'success'); reload(true) } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  const num = (k, step = 1) => (
    <input type="number" className="input" style={{ width: 120 }} step={step} value={f[k]} disabled={!ed} aria-label={k}
      onChange={(e) => setF({ ...f, [k]: e.target.value === '' ? '' : Number(e.target.value) })} />
  )
  return (
    <>
      <PageHead eyebrow="Configuration" icon={SettingsIcon} title="Settings" lead={ed ? 'Profile, appearance and system configuration.' : 'Your profile and appearance. System settings are managed by administrators.'} />
      <div className="grid g2">
        <div className="card">
          <div className="card-head"><h3><UsersIcon />Profile</h3></div>
          <div className="card-body">
            <div className="kv">
              <div>Name</div><div>{user.name}</div><div>Email</div><div>{user.email}</div>
              <div>Role</div><div><RoleBadge role={user.role} label={user.role_label} /></div>
              <div>Permissions</div><div className="row wrap" style={{ gap: 5 }}>{permissions.map((p) => <span key={p} className="badge b-neutral mono" style={{ fontSize: 10.5 }}>{p}</span>)}</div>
            </div>
          </div>
        </div>
        <SecurityCard />
        <div className="card">
          <div className="card-head"><h3><Palette />Appearance</h3></div>
          <div className="card-body stack">
            <div className="row between"><div><b className="small">Dark theme</b><div className="tiny faint">The animated background adapts automatically.</div></div>
              <button className={`switch ${theme === 'dark' ? 'on' : ''}`} role="switch" aria-checked={theme === 'dark'} aria-label="Dark theme" onClick={toggleTheme} /></div>
            <div className="row between"><div><b className="small">Guided demo panel</b><div className="tiny faint">Show the 10-step walkthrough.</div></div>
              <button className={`switch ${demo.open ? 'on' : ''}`} role="switch" aria-checked={demo.open} aria-label="Guided demo panel" onClick={() => (demo.caseId ? demo.setGuide({ open: !demo.open, min: false }) : demo.launch())} /></div>
            <p className="tiny faint">Animations respect your operating system's reduced-motion preference.</p>
          </div>
        </div>
        <div className="card">
          <div className="card-head"><h3><SlidersHorizontal />Analysis settings</h3>{!ed && <span className="badge b-neutral">Read-only</span>}</div>
          <div className="card-body stack">
            <div className="field"><label htmlFor="org">Organisation name (report header)</label><input id="org" className="input" value={f.organization_name} disabled={!ed} onChange={(e) => setF({ ...f, organization_name: e.target.value })} /></div>
            <div className="row between"><div><b className="small">OCR for images & scanned PDFs</b><div className="tiny faint">Engine: {data.system.ocr_engine}</div></div>
              <button className={`switch ${f.ocr_enabled ? 'on' : ''}`} role="switch" aria-checked={f.ocr_enabled} aria-label="OCR enabled" disabled={!ed} onClick={() => ed && setF({ ...f, ocr_enabled: !f.ocr_enabled })} /></div>
            <div className="row between"><div><b className="small">Maximum upload size (MB)</b><div className="tiny faint">1–100</div></div>{num('max_upload_mb')}</div>
            <div className="row between"><div><b className="small">Content similarity threshold</b><div className="tiny faint">TF-IDF cosine needed to count as “Similar Content”</div></div>{num('similarity_threshold', 0.01)}</div>
            <div className="row between"><div><b className="small">Minimum relationship score</b><div className="tiny faint">Signals below this are not shown</div></div>{num('relationship_min_score', 0.01)}</div>
            <div className="row between"><div><b className="small">Name-variation threshold</b><div className="tiny faint">Similarity treated as a “slight variation”</div></div>{num('name_variation_threshold', 0.01)}</div>
            <div className="row between"><div><b className="small">Low OCR confidence (%)</b><div className="tiny faint">Below this, a record requires review</div></div>{num('low_ocr_confidence')}</div>
            {ed && <div className="row"><Button variant="primary" icon={Save} loading={busy} onClick={save}>Save settings</Button><span className="tiny faint">Applies to new uploads and re-run analyses.</span></div>}
          </div>
        </div>
        <div className="card">
          <div className="card-head"><h3><Cpu />System</h3></div>
          <div className="card-body stack">
            <div className="kv">
              <div>Database</div><div className="row" style={{ gap: 6 }}><Database size={14} />{data.system.database}</div>
              <div>File storage</div><div>{data.system.storage}</div>
              <div>Integrity</div><div>{data.system.hash_algorithm}</div>
              <div>OCR engine</div><div>{data.system.ocr_engine}</div>
              <div>NLP</div><div>{data.system.nlp}</div>
              <div>Accepted types</div><div>{data.system.allowed_types.join(', ')}</div>
              <div>Version</div><div>{data.system.version}</div>
            </div>
            <Link to="/api/docs" target="_blank" reloadDocument className="small">Open the API reference (OpenAPI)</Link>
            {ed && <>
              <div className="divider" />
              <div className="row between wrap"><div><b className="small">Reset synthetic demo data</b><div className="tiny faint">Rebuilds the three demo cases through the full pipeline (~10–20s).</div></div>
                <Button variant="warn" icon={RefreshCw} onClick={() => setReset(true)}>Reset demo</Button></div>
            </>}
          </div>
        </div>
      </div>
      {reset && <Confirm title="Reset demo data?" message="All synthetic demo cases (including their review decisions and reports) are deleted and rebuilt from the original demo files. Non-demo cases are untouched."
        confirmLabel="Reset demo data" onClose={() => setReset(false)}
        onConfirm={async () => { try { await api.post('/settings/reset-demo'); toast('Synthetic demo data restored', 'success'); demo.setGuide({ caseId: null, open: false, done: [] }) } catch (e) { toast(e.message, 'error') } setReset(false) }} />}
    </>
  )
}
