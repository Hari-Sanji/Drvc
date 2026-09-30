import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertOctagon, AlertTriangle, CalendarClock, CheckCircle2, Clock, FileText, Layers } from 'lucide-react'
import { Empty, fmtIsoDate } from '../ui'

const FLAG_INFO = {
  conflict: ['b-red', 'Conflicting date', AlertOctagon],
  review: ['b-amber', 'Requires review', AlertTriangle],
  resolved: ['b-green', 'Reviewed', CheckCircle2],
  normal: ['b-neutral', 'Normal', CheckCircle2],
}

export default function Timeline({ events, counts }) {
  const [filter, setFilter] = useState('all')
  const [mentions, setMentions] = useState(false)
  const navigate = useNavigate()
  const list = useMemo(() => events.filter((e) =>
    (mentions || e.kind !== 'mention' || e.flag !== 'normal') &&
    (filter === 'all' || e.flag === filter)), [events, filter, mentions])

  if (!events.length) {
    return <Empty icon={CalendarClock} title="No events yet">No dated events were extracted from the analysed records. Upload records containing dates to build a chronology.</Empty>
  }
  let lastYear = null
  return (
    <div>
      <div className="row wrap between" style={{ marginBottom: 14 }}>
        <div className="seg" role="group" aria-label="Filter events">
          {[['all', `All (${events.length})`], ['conflict', `Conflicting (${counts?.conflict ?? 0})`], ['review', `Requires review (${counts?.review ?? 0})`], ['normal', 'Normal']].map(([k, l]) => (
            <button key={k} className={filter === k ? 'active' : ''} onClick={() => setFilter(k)} aria-pressed={filter === k}>{l}</button>
          ))}
        </div>
        <label className="checkbox"><input type="checkbox" checked={mentions} onChange={(e) => setMentions(e.target.checked)} />Show unlabelled date mentions</label>
      </div>
      {!list.length && <Empty icon={CalendarClock} title="No events match this filter" />}
      <div className="tl">
        {list.map((e, i) => {
          const y = e.date.slice(0, 4)
          const showYear = y !== lastYear
          lastYear = y
          const [cls, label, Icon] = FLAG_INFO[e.flag] || FLAG_INFO.normal
          return (
            <div key={e.id}>
              {showYear && <div className="tl-year"><span>{y}</span></div>}
              <div className={`tl-item ${i % 2 ? 'right' : 'left'} ${e.flag}`} style={{ animationDelay: `${Math.min(i, 24) * 70}ms` }}>
                <div className="tl-dot" aria-hidden />
                <div className="card tl-card" role="button" tabIndex={0} aria-label={`${e.label} on ${e.date_label}, stated in ${e.sources?.length || 1} record(s). Open source record.`}
                  onClick={() => navigate(`/app/records/${e.record_id}`)} onKeyDown={(k) => k.key === 'Enter' && navigate(`/app/records/${e.record_id}`)}>
                  <div className="row between wrap" style={{ gap: 8 }}>
                    <div className="tl-date"><CalendarClock size={14} />{fmtIsoDate(e.date)}{e.time && <span className="row faint" style={{ gap: 4 }}><Clock size={12} />{e.time}</span>}</div>
                    {e.flag !== 'normal' && <span className={`badge ${cls} ${e.flag === 'conflict' ? 'pulse-red' : ''}`}><Icon />{label}</span>}
                  </div>
                  <div style={{ fontWeight: 600, marginTop: 6 }}>{e.label}</div>
                  {(e.sources?.length || 0) > 1 ? (
                    <>
                      <div className="row small muted" style={{ marginTop: 6, gap: 6 }}><Layers size={13} />Stated in {e.sources.length} records</div>
                      <div className="sources" onClick={(ev) => ev.stopPropagation()}>
                        {e.sources.map((s) => <Link key={s.id} to={`/app/records/${s.id}`} className={s.flag === 'conflict' ? 'conflict' : ''} title={s.snippet}>{s.doc_type || s.filename}</Link>)}
                      </div>
                    </>
                  ) : <div className="row small muted" style={{ marginTop: 6, gap: 6 }}><FileText size={13} /><span className="truncate">{e.source?.filename}</span></div>}
                  {e.snippet && <div className="tiny faint mono truncate" style={{ marginTop: 6 }} title={e.snippet}>“{e.snippet}”</div>}
                  <div className="row tiny faint" style={{ marginTop: 8, gap: 8 }}>
                    Confidence <div className="conf-bar"><span style={{ width: `${e.confidence * 100}%`, background: e.confidence < 0.6 ? 'var(--amber)' : 'var(--cyan)' }} /></div>{Math.round(e.confidence * 100)}%
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
