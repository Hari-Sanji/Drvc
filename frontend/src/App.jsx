import { Suspense, lazy } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Compass, ShieldOff } from 'lucide-react'
import { AuthProvider, useAuth } from './auth'
import Background from './components/Background'
import Layout from './components/Layout'
import { DemoProvider } from './demo'
import { Landing, Login } from './pages/Public'
import { Empty, Loading, ToastProvider } from './ui'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Cases = lazy(() => import('./pages/Cases'))
const CaseWorkspace = lazy(() => import('./pages/CaseWorkspace'))
const Records = lazy(() => import('./pages/Records'))
const RecordDetail = lazy(() => import('./pages/RecordDetail'))
const Audit = lazy(() => import('./pages/Audit'))
const TimelinePage = lazy(() => import('./pages/Center').then((m) => ({ default: m.TimelinePage })))
const GraphPage = lazy(() => import('./pages/Center').then((m) => ({ default: m.GraphPage })))
const ConflictCenter = lazy(() => import('./pages/Center').then((m) => ({ default: m.ConflictCenter })))
const ReviewCenter = lazy(() => import('./pages/Center').then((m) => ({ default: m.ReviewCenter })))
const ReportsPage = lazy(() => import('./pages/Center').then((m) => ({ default: m.ReportsPage })))
const SearchPage = lazy(() => import('./pages/Center').then((m) => ({ default: m.SearchPage })))
const Users = lazy(() => import('./pages/Admin').then((m) => ({ default: m.Users })))
const Settings = lazy(() => import('./pages/Admin').then((m) => ({ default: m.Settings })))

function RequireAuth({ children }) {
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <div style={{ position: 'relative', zIndex: 1 }}><Loading label="Restoring session…" /></div>
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />
  return children
}

function Guard({ perm, children }) {
  const { can } = useAuth()
  if (!can(perm)) {
    return <div className="card"><Empty icon={ShieldOff} title="Not available for your role" action={<Link className="btn" to="/app/dashboard">Back to dashboard</Link>}>
      Your role does not include this permission. Access is enforced by the server — the API returns an authorization error for this section.</Empty></div>
  }
  return children
}

function NotFound() {
  return <div className="card" style={{ position: 'relative', zIndex: 1 }}><Empty icon={Compass} title="Page not found" action={<Link className="btn primary" to="/app/dashboard">Go to dashboard</Link>}>The page you requested does not exist.</Empty></div>
}

const S = ({ children }) => <Suspense fallback={<Loading />}>{children}</Suspense>

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <DemoProvider>
            <Background />
            <a href="#main" className="sr-only">Skip to content</a>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<Login />} />
              <Route path="/app" element={<RequireAuth><Layout /></RequireAuth>}>
                <Route index element={<Navigate to="dashboard" replace />} />
                <Route path="dashboard" element={<S><Dashboard /></S>} />
                <Route path="cases" element={<S><Guard perm="case:view"><Cases /></Guard></S>} />
                <Route path="cases/:id" element={<S><CaseWorkspace /></S>} />
                <Route path="cases/:id/:tab" element={<S><CaseWorkspace /></S>} />
                <Route path="records" element={<S><Guard perm="record:view"><Records /></Guard></S>} />
                <Route path="records/:id" element={<S><RecordDetail /></S>} />
                <Route path="timeline" element={<S><TimelinePage /></S>} />
                <Route path="graph" element={<S><GraphPage /></S>} />
                <Route path="conflicts" element={<S><ConflictCenter /></S>} />
                <Route path="review" element={<S><ReviewCenter /></S>} />
                <Route path="reports" element={<S><Guard perm="report:view"><ReportsPage /></Guard></S>} />
                <Route path="audit" element={<S><Guard perm="audit:view"><Audit /></Guard></S>} />
                <Route path="users" element={<S><Guard perm="user:manage"><Users /></Guard></S>} />
                <Route path="settings" element={<S><Settings /></S>} />
                <Route path="search" element={<S><SearchPage /></S>} />
                <Route path="*" element={<NotFound />} />
              </Route>
              <Route path="*" element={<div className="content"><NotFound /></div>} />
            </Routes>
          </DemoProvider>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  )
}
