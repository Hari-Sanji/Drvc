import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpenCheck, CheckCircle2, Circle, Download, Eye, FileDown, FileJson, FilePlus2, FileText, Fingerprint } from 'lucide-react'
import { api, downloadFile } from '../api'
import { useAuth } from '../auth'
import { useDemo } from '../demo'
import { Button, Empty, Modal, fmtDateTime, shortHash, useToast } from '../ui'

const SECTIONS = ['Case details', 'Record list', 'SHA-256 hashes', 'Metadata', 'Extracted information', 'Entities', 'Events & timeline',
  'Relationship summary', 'Conflict summary', 'Review actions', 'Audit information', 'Limitations & disclaimer']

export function GenerateReport({ caseId, onClose, onDone }) {
  const [step, setStep] = useState(-1)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState('')
  const toast = useToast()
  const demo = useDemo()

  const run = async () => {
    setErr(''); setStep(0)
    const req = api.post(`/cases/${caseId}/reports`)
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    for (let i = 1; i <= SECTIONS.length; i++) {
      await new Promise((r) => setTimeout(r, reduce ? 0 : 170))
      setStep(i)
    }
    try {
      const r = await req
      setResult(r)
      toast('Verification report generated', 'success')
      if (demo?.caseId === caseId) demo.markDone('report')
      onDone?.(r)
    } catch (e) { setErr(e.message); setStep(-1) }
  }
  return (
    <Modal title="Generate verification report" icon={BookOpenCheck} onClose={onClose} size="wide" footer={
      result ? <>
        <Button variant="ghost" icon={FileJson} onClick={() => downloadFile(`/reports/${result.id}/download?format=json`, `DRCV-Report-${result.case_code}-${result.id}.json`)}>JSON</Button>
        <Button icon={Download} onClick={() => downloadFile(`/reports/${result.id}/download`, `DRCV-Report-${result.case_code}-${result.id}.html`)}>HTML</Button>
        <Button icon={FileText} onClick={() => downloadFile(`/reports/${result.id}/download?format=summary`, `DRCV-Summary-${result.case_code}-${result.id}.pdf`)}>Summary PDF</Button>
        <Button variant="primary" icon={FileDown} onClick={() => downloadFile(`/reports/${result.id}/download?format=pdf`, `DRCV-Report-${result.case_code}-${result.id}.pdf`)}>Download PDF</Button>
      </> : <><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" icon={FilePlus2} loading={step >= 0} onClick={run}>Assemble report</Button></>
    }>
      <p className="small muted" style={{ marginBottom: 14 }}>The report is assembled from the current database state and fingerprinted with SHA-256 so later copies can be checked for changes.</p>
      <div className="assembly">
        {SECTIONS.map((s, i) => (
          <div key={s} className={step > i || result ? 'on' : ''}>{step > i || result ? <CheckCircle2 /> : step === i ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <Circle />}{s}</div>
        ))}
      </div>
      {err && <div className="form-error" role="alert" style={{ marginTop: 12 }}>{err}</div>}
      {result && (
        <div className="card pad" style={{ marginTop: 16, borderColor: 'rgba(16,185,129,.35)' }}>
          <div className="row"><CheckCircle2 color="var(--green-2)" /><b>{result.title}</b></div>
          <div className="row tiny mono" style={{ marginTop: 8, color: 'var(--cyan-2)', gap: 6 }}><Fingerprint size={12} />Report SHA-256 {result.sha256}</div>
          <p className="tiny faint" style={{ marginTop: 8 }}>{result.summary.records} records · {result.summary.relationships} relationship signals · {result.summary.conflicts} potential inconsistencies ({result.summary.unresolved} open) · {result.summary.reviews} review actions</p>
        </div>
      )}
      <p className="tiny faint" style={{ marginTop: 14 }}>Disclaimer included: this report presents extracted digital evidence signals. It does not establish absolute authenticity or prove a real-world event.</p>
    </Modal>
  )
}

export function ReportPreview({ report, onClose }) {
  const [html, setHtml] = useState(null)
  useEffect(() => { api.get(`/reports/${report.id}/download`).then((h) => setHtml(h.replace(/<div class='noprint'>[\s\S]*?<\/div>/, ''))).catch((e) => setHtml(`<p style="font-family:sans-serif;padding:20px">${e.message}</p>`)) }, [report.id])
  return (
    <Modal title={report.title} icon={Eye} onClose={onClose} size="xl" footer={
      <Button variant="primary" icon={Download} onClick={() => downloadFile(`/reports/${report.id}/download`, `DRCV-Report-${report.case_code}-${report.id}.html`)}>Download HTML</Button>
    }>
      {html == null ? <div className="center-load"><span className="spinner" /></div> : <iframe className="report-frame" title="Report preview" sandbox="allow-modals" srcDoc={html} />}
    </Modal>
  )
}

export function ReportList({ reports, showCase }) {
  const [preview, setPreview] = useState(null)
  if (!reports.length) return <Empty icon={BookOpenCheck} title="No reports yet">Generate a verification report to capture the current evidence signals, review decisions and audit trail.</Empty>
  return (
    <>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Report</th>{showCase && <th>Case</th>}<th>Generated</th><th>Contents</th><th>Fingerprint</th><th /></tr></thead>
          <tbody>
            {reports.map((r) => (
              <tr key={r.id}>
                <td><b>{r.title}</b><div className="tiny faint">by {r.created_by}</div></td>
                {showCase && <td><Link to={`/app/cases/${r.case_id}/reports`}>{r.case_code}</Link><div className="tiny faint">{r.case_name}</div></td>}
                <td className="small">{fmtDateTime(r.created_at)}</td>
                <td className="small muted">{r.summary.records} records · {r.summary.conflicts} conflicts ({r.summary.unresolved} open)</td>
                <td className="mono tiny" style={{ color: 'var(--cyan-2)' }}>{shortHash(r.sha256)}</td>
                <td><div className="row" style={{ justifyContent: 'flex-end' }}>
                  <Button size="sm" icon={Eye} onClick={() => setPreview(r)}>Preview</Button>
                  <Button size="sm" variant="primary" icon={FileDown} aria-label={`Download ${r.title} as PDF`} onClick={() => downloadFile(`/reports/${r.id}/download?format=pdf`, `DRCV-Report-${r.case_code}-${r.id}.pdf`)}>PDF</Button>
                  <Button size="sm" icon={FileText} aria-label="Download executive summary PDF" onClick={() => downloadFile(`/reports/${r.id}/download?format=summary`, `DRCV-Summary-${r.case_code}-${r.id}.pdf`)}>Summary</Button>
                  <Button size="sm" variant="ghost" icon={Download} aria-label={`Download ${r.title} as HTML`} onClick={() => downloadFile(`/reports/${r.id}/download`, `DRCV-Report-${r.case_code}-${r.id}.html`)}>HTML</Button>
                  <Button size="sm" variant="ghost" icon={FileJson} aria-label="Download JSON" onClick={() => downloadFile(`/reports/${r.id}/download?format=json`, `DRCV-Report-${r.case_code}-${r.id}.json`)} />
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {preview && <ReportPreview report={preview} onClose={() => setPreview(null)} />}
    </>
  )
}

export function useCanGenerate() {
  const { can } = useAuth()
  return can('report:generate')
}
