import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api } from './api.js'
import { Home, Research, Opportunities, Studio, Library, ListingStudio, Analytics, Settings } from './pages.jsx'

export const Ctx = createContext(null)
export const useApp = () => useContext(Ctx)

const NAV = [
  ['home', 'Dashboard'], ['research', 'Market Research'], ['opportunities', 'Opportunity Explorer'],
  ['studio', 'Design Studio'], ['library', 'Product Library'], ['listing', 'Listing Studio'],
  ['analytics', 'Analytics'], ['settings', 'Settings'],
]

function parseHash() {
  const h = window.location.hash.replace(/^#\/?/, '')
  const [path, query] = h.split('?')
  const [page, id] = (path || 'home').split('/')
  return { page: page || 'home', id: id ? Number(id) : null, query: new URLSearchParams(query || '') }
}

export function go(page, id) { window.location.hash = `#/${page}${id ? '/' + id : ''}` }

export default function App() {
  const [route, setRoute] = useState(parseHash())
  const [status, setStatus] = useState(null)
  const [jobs, setJobs] = useState([])
  const [watch, setWatch] = useState([])
  const [toast, setToast] = useState(null)

  useEffect(() => { const f = () => setRoute(parseHash()); window.addEventListener('hashchange', f); return () => window.removeEventListener('hashchange', f) }, [])
  const refreshStatus = useCallback(() => api('/api/status').then(setStatus).catch(e => setToast({ err: true, msg: e.message })), [])
  useEffect(() => { refreshStatus() }, [refreshStatus])

  // poll watched jobs
  useEffect(() => {
    if (!watch.length) return
    const t = setInterval(async () => {
      const res = await Promise.all(watch.map(id => api(`/api/jobs/${id}`).catch(() => null)))
      const list = res.filter(Boolean)
      setJobs(list)
      const finished = list.filter(j => j.status === 'done' || j.status === 'failed')
      if (finished.length) {
        finished.forEach(j => window.dispatchEvent(new CustomEvent('job-finished', { detail: j })))
        setWatch(w => w.filter(id => !finished.find(j => j.id === id)))
        setTimeout(() => setJobs(js => js.filter(j => !finished.find(f => f.id === j.id))), 8000)
        refreshStatus()
      }
    }, 1200)
    return () => clearInterval(t)
  }, [watch, refreshStatus])

  const track = (jobId) => { setWatch(w => [...new Set([...w, jobId])]) }
  const notify = (msg, err = false) => { setToast({ msg, err }); setTimeout(() => setToast(null), 6000) }
  const retry = async (id) => { await api(`/api/jobs/${id}/retry`, { method: 'POST' }); track(id) }

  const Page = { home: Home, research: Research, opportunities: Opportunities, studio: Studio, library: Library,
    listing: ListingStudio, analytics: Analytics, settings: Settings }[route.page] || Home

  return (
    <Ctx.Provider value={{ status, refreshStatus, track, notify, route }}>
      <div className="app">
        <aside className="side">
          <div className="brand">Digital Product Studio<small>Research · Design · List</small></div>
          {NAV.map(([k, label]) => <a key={k} className={'nav' + (route.page === k ? ' active' : '')} href={`#/${k}`}>{label}</a>)}
          <div className="foot">{status?.attribution}</div>
        </aside>
        <main><Page id={route.id} query={route.query} /></main>
      </div>
      <div className="tray">
        {toast && <div className={'card notice ' + (toast.err ? 'err' : 'info')}>{toast.msg}</div>}
        {jobs.map(j => <JobCard key={j.id} job={j} onRetry={() => retry(j.id)} />)}
      </div>
    </Ctx.Provider>
  )
}

const LABEL = { research: 'Researching opportunities', generate_product: 'Generating product', revise_product: 'Applying revision',
  variations: 'Rendering variations', send_to_etsy: 'Sending draft to Etsy', daily_automation: 'Daily automation' }

export function JobCard({ job, onRetry }) {
  return (
    <div className="card">
      <div className="row between"><b>{LABEL[job.kind] || job.kind}</b>
        <span className={'pill ' + (job.status === 'done' ? 'ok' : job.status === 'failed' ? 'err' : 'blue')}>{job.status}</span></div>
      <div className="bar" style={{ margin: '8px 0' }}><i style={{ width: `${job.progress}%` }} /></div>
      <div className="small muted">{job.message}</div>
      {job.steps?.length > 0 && <div className="steps">{job.steps.map(s => <div key={s.name}>
        {s.status === 'done' ? '✔' : s.status === 'failed' ? '✖' : '…'} {s.name}{s.detail ? ` — ${s.detail}` : ''}</div>)}</div>}
      {job.status === 'failed' && <div className="col" style={{ marginTop: 8 }}>
        <div className="small" style={{ color: 'var(--err)' }}>{job.error}</div>
        <button className="btn sm" onClick={onRetry}>Retry</button></div>}
    </div>
  )
}

export function Bar({ value, max = 100 }) { return <div className="bar"><i style={{ width: `${Math.min(100, (value / max) * 100)}%` }} /></div> }

export function Modal({ children, onClose }) {
  return <div className="modal" onClick={onClose}><div className="card" onClick={e => e.stopPropagation()}>
    <div className="row between" style={{ marginBottom: 10 }}><span /><button className="btn sm" onClick={onClose}>Close</button></div>{children}</div></div>
}

// run a job and call back when finished
export function useJobRunner() {
  const { track, notify } = useApp()
  return useCallback(async (path, body, onDone) => {
    try {
      const { job_id } = await api(path, { method: 'POST', body })
      track(job_id)
      const handler = (e) => {
        if (e.detail.id !== job_id) return
        window.removeEventListener('job-finished', handler)
        if (e.detail.status === 'failed') notify(`Failed: ${e.detail.error}`, true)
        else notify(e.detail.result?.message || 'Done')
        onDone && onDone(e.detail)
      }
      window.addEventListener('job-finished', handler)
      return job_id
    } catch (e) { notify(e.message, true) }
  }, [track, notify])
}
