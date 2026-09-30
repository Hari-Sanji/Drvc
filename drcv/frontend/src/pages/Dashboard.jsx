import { Link, useNavigate } from 'react-router-dom'
import {
  Activity, AlertOctagon, ArrowRight, BookOpenCheck, CheckCircle2, ClipboardCheck, FileStack, FileUp, Fingerprint, FolderKanban,
  GitMerge, Link2, PieChart, Radar, Rocket, ScanSearch, ShieldAlert, ShieldCheck, XCircle,
} from 'lucide-react'
import { api } from '../api'
import { useAuth } from '../auth'
import { AreaChart, BarList, Donut, Legend, SERIES } from '../components/Charts'
import { useDemo } from '../demo'
import { BrandFlow, Button, Counter, ErrorState, PageHead, Principle, Skeleton, StatusBadge, Synthetic, timeAgo, useAsync, useInterval } from '../ui'

const FEED_ICON = {
  upload: [FileUp, 'ic-blue'], pipeline: [ScanSearch, 'ic-cyan'], conflict: [AlertOctagon, 'ic-red'], review: [ClipboardCheck, 'ic-green'],
  report: [BookOpenCheck, 'ic-violet'], case: [FolderKanban, 'ic-blue'], analysis: [Radar, 'ic-pink'], integrity: [Fingerprint, 'ic-cyan'],
}

export default function Dashboard() {
  const { user } = useAuth()
  const demo = useDemo()
  const navigate = useNavigate()
  const { data, error, loading, reload } = useAsync(() => api.get('/dashboard'), [])
  useInterval(() => reload(true), 15000)

  if (error) return <ErrorState error={error} onRetry={reload} />
  const s = data?.stats
  const stats = [
    ['Total Records', s?.total_records, FileStack, 'ic-violet', '#d97745', 'Across active cases'],
    ['Integrity Verified', s?.integrity_verified, ShieldCheck, 'ic-cyan', '#e8c39e', 'SHA-256 fingerprint recorded'],
    ['Related Records', s?.related_records, Link2, 'ic-blue', '#a8978a', `${s?.relationships ?? 0} relationship signals`],
    ['Potential Conflicts', s?.potential_conflicts, AlertOctagon, 'ic-red', '#f43f5e', `${s?.resolved ?? 0} already reviewed`],
    ['Requires Review', s?.requires_review, ClipboardCheck, 'ic-amber', '#f59e0b', 'Unresolved review items'],
  ]
  const hour = new Date().getHours()
  return (
    <>
      <PageHead eyebrow="Intelligence overview" icon={Radar}
        title={`Good ${hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening'}, ${user?.name?.split(' ')[0]}`}
        lead="Live view of every analysed record, relationship signal and potential inconsistency across your cases."
        actions={<><Button icon={FolderKanban} onClick={() => navigate('/app/cases')}>Open cases</Button><Button variant="primary" icon={Rocket} onClick={demo.launch}>Launch Demo</Button></>} />
      <div className="card pad" style={{ marginBottom: 18 }}>
        <div className="row wrap between" style={{ gap: 16 }}>
          <BrandFlow />
          <span className="small muted">Pipeline: hash → metadata → OCR → entities → events → similarity → relationships → conflicts → human review</span>
        </div>
      </div>
      <div className="grid g5" style={{ marginBottom: 18 }}>
        {stats.map(([label, v, I, ic, c, foot], i) => (
          <div key={label} className="card stat hover" style={{ '--c': c, animation: `page-in .5s ${i * 70}ms both` }}>
            <div className={`stat-icon ${ic}`}><I /></div>
            {loading && !data ? <Skeleton h={30} w="50%" /> : <div className="stat-value"><Counter value={v || 0} /></div>}
            <div className="stat-label">{label}</div>
            <div className="stat-foot">{foot}</div>
          </div>
        ))}
      </div>
      <div className="grid g3" style={{ marginBottom: 18 }}>
        <div className="card span2">
          <div className="card-head"><h3><Activity />Processing activity</h3><Legend items={[['Records processed', SERIES[0]], ['Review actions', SERIES[1]]]} /></div>
          <div className="card-body">{data ? <AreaChart data={data.activity} series={[{ key: 'processed', label: 'Records processed', color: SERIES[0] }, { key: 'reviews', label: 'Review actions', color: SERIES[1] }]} /> : <Skeleton h={220} />}</div>
        </div>
        <div className="card">
          <div className="card-head"><h3><PieChart />Case status</h3></div>
          <div className="card-body">{data ? <Donut label="Cases" items={[
            { label: 'Active', value: data.case_status.active, color: SERIES[0] },
            { label: 'Processing', value: data.case_status.processing, color: SERIES[1] },
            { label: 'Under Review', value: data.case_status.requires_review, color: SERIES[2] },
            { label: 'Completed', value: data.case_status.completed, color: SERIES[3] },
          ]} /> : <Skeleton h={180} />}</div>
        </div>
      </div>
      <div className="grid g3">
        <div className="card">
          <div className="card-head"><h3><ShieldAlert />Conflict distribution</h3><Link to="/app/conflicts" className="small">Conflict Center</Link></div>
          <div className="card-body">
            {data ? <BarList color="#e11d48" items={Object.entries(data.conflict_distribution).map(([label, value]) => ({ label, value }))} /> : <Skeleton h={150} />}
            <p className="tiny faint" style={{ marginTop: 14 }}>Potential inconsistencies only — each one is routed to a human reviewer.</p>
          </div>
        </div>
        <div className="card">
          <div className="card-head"><h3><GitMerge />Recent activity</h3><Link to="/app/audit" className="small">Audit log</Link></div>
          <div className="card-body" style={{ paddingTop: 6, maxHeight: 380, overflowY: 'auto' }}>
            {!data && <Skeleton h={200} />}
            {data?.recent.length === 0 && <p className="small muted">No activity yet.</p>}
            {data?.recent.map((a, i) => {
              const [I, ic] = a.result === 'failed' ? [XCircle, 'ic-red'] : FEED_ICON[a.category] || [CheckCircle2, 'ic-violet']
              return (
                <div key={a.id} className="feed-item" style={{ animationDelay: `${i * 40}ms` }}>
                  <div className={`feed-ic ${ic}`}><I /></div>
                  <div className="grow" style={{ minWidth: 0 }}>
                    <div className="small" style={{ fontWeight: 600 }}>{a.action}</div>
                    <div className="tiny faint truncate">{a.target && <>{a.target} · </>}{a.user} · {timeAgo(a.ts)}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
        <div className="card">
          <div className="card-head"><h3><FolderKanban />Cases</h3><Link to="/app/cases" className="small">All cases</Link></div>
          <div className="card-body stack" style={{ gap: 10 }}>
            {!data && <Skeleton h={180} />}
            {data?.cases.length === 0 && <p className="small muted">No cases yet. Create your first case to begin record analysis.</p>}
            {data?.cases.slice(0, 6).map((c) => (
              <Link key={c.id} to={`/app/cases/${c.id}`} className="chip" style={{ color: 'var(--text)', textDecoration: 'none', justifyContent: 'space-between', padding: '10px 12px' }}>
                <span style={{ minWidth: 0 }}><b className="truncate" style={{ display: 'block' }}>{c.name}</b><span className="tiny faint">{c.code}</span></span>
                <StatusBadge kind="case" status={c.status} />
              </Link>
            ))}
            {data?.cases.some((c) => c.is_demo) && <div><Synthetic /></div>}
            <Button variant="ghost" iconRight={ArrowRight} onClick={demo.launch}>Run the guided demo</Button>
          </div>
        </div>
      </div>
      <div style={{ marginTop: 18 }}><Principle /></div>
    </>
  )
}
