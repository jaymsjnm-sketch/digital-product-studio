import React, { useEffect, useMemo, useState } from 'react'
import { api, fileUrl, money, pct, fmtBytes } from './api.js'
import { useApp, go, Bar, Modal, useJobRunner } from './App.jsx'

const FACTOR_LABEL = { demand: 'Demand & growth', competition: 'Competition & differentiation', profitability: 'Expected profitability',
  automation: 'Automation feasibility', bundle: 'Bundle & personalization', seasonal: 'Seasonal / long-term' }
const STATUS_PILL = { review: 'blue', approved: 'ok', published: 'ok', rejected: 'err', needs_attention: 'warn', draft: '' }

function useLoad(fn, deps = []) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const reload = () => fn().then(d => { setData(d); setErr(null) }).catch(e => setErr(e.message))
  useEffect(() => { reload() }, deps) // eslint-disable-line
  useEffect(() => { const h = () => reload(); window.addEventListener('job-finished', h); return () => window.removeEventListener('job-finished', h) }, deps) // eslint-disable-line
  return [data, reload, err]
}

const Score = ({ v, label = 'score' }) => <div className="kpi"><b className="score">{Math.round(v ?? 0)}</b><span>{label}</span></div>
const Pill = ({ k, children }) => <span className={'pill ' + (STATUS_PILL[k] ?? '')}>{children || k}</span>
const Err = ({ e }) => e ? <div className="notice err">{e}</div> : null
const conf = (c) => c >= 60 ? 'ok' : c >= 35 ? 'warn' : 'err'

// =============================================================== HOME
export function Home() {
  const { status } = useApp()
  const run = useJobRunner()
  const [recs, reloadRecs] = useLoad(() => api('/api/recommendations?n=5'))
  const [prods] = useLoad(() => api('/api/products'))
  const c = status?.credentials || {}
  return (<div className="col" style={{ gap: 18 }}>
    <div><h1>Dashboard</h1><p className="sub">Find what to sell, create original products, and prepare Etsy listings. You approve everything before it goes live.</p></div>
    <div className="card col">
      <div className="flow">{['Research', 'Rank', 'Select', 'Generate designs', 'Quality check', 'Review', 'Bundle', 'Listing', 'Approve', 'Publish (draft)'].map((s, i) =>
        <React.Fragment key={s}>{i > 0 && <i>→</i>}<span>{s}</span></React.Fragment>)}</div>
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn primary big" onClick={() => run('/api/research/run', {}, reloadRecs)}>Research Opportunities</button>
        <button className="btn big" onClick={() => go('opportunities')}>Explore ranked opportunities</button>
        <button className="btn big" onClick={() => go('library')}>Product library</button>
      </div>
      {status?.last_research && <div className="small muted">Last research: {new Date(status.last_research.started_at).toLocaleString()} · sources: {status.last_research.sources.join(', ')}</div>}
    </div>
    {status && !c.etsy_api_key && <div className="notice">Live Etsy marketplace data is off. Rankings currently use dated, cited public research and labelled assumptions (lower confidence). Add an Etsy API key in <a href="#/settings">Settings</a> to add live listing counts, prices, favorites and views.</div>}
    <div className="grid g4">
      <div className="card kpi"><b>{status?.counts.opportunities ?? '–'}</b><span>ranked opportunities</span></div>
      <div className="card kpi"><b>{status?.counts.products ?? '–'}</b><span>products created</span></div>
      <div className="card kpi"><b>{status?.counts.approved ?? '–'}</b><span>approved / published</span></div>
      <div className="card kpi"><b>{money(status?.budget.today_usd)}</b><span>API spend today (limit {money(status?.budget.daily_limit_usd)})</span></div>
    </div>
    <div className="grid g2">
      <div className="card"><h2>Top recommendations</h2>
        {!recs?.length && <div className="empty">Click “Research Opportunities” to rank ideas.</div>}
        <table><tbody>{recs?.map(o => <tr key={o.id}>
          <td><b>{o.concept}</b><div className="small muted">Score {o.score} · confidence <span className={'pill ' + conf(o.confidence)}>{o.confidence}</span></div></td>
          <td style={{ textAlign: 'right' }}><button className="btn sm" onClick={() => go('opportunities', o.id)}>Details</button>{' '}
            <button className="btn sm primary" onClick={() => run('/api/products/generate', { opportunity_id: o.id }, (j) => go('studio', j.result?.product_id))}>Generate Product</button></td></tr>)}</tbody></table>
      </div>
      <div className="card"><h2>Recent products</h2>
        {!prods?.length && <div className="empty">No products yet.</div>}
        <div className="thumbs">{prods?.slice(0, 6).map(p => <div key={p.id} className="thumb" onClick={() => go('studio', p.id)}>
          <img src={fileUrl(p.hero_preview)} alt="" /><div className="small"><b>{p.name}</b></div>
          <div className="row"><Pill k={p.status} /><span className="small muted">QC {p.qc_score ?? '–'}</span></div></div>)}</div>
      </div>
    </div>
  </div>)
}

// =============================================================== MARKET RESEARCH
export function Research() {
  const run = useJobRunner()
  const { notify, status } = useApp()
  const [niches, reload, err] = useLoad(() => api('/api/niches'))
  const [runs] = useLoad(() => api('/api/research/runs'))
  const [open, setOpen] = useState(null)
  const [ev, setEv] = useState({ claim: '', url: '', source_title: '', published: '' })
  const upload = async (e) => {
    const f = e.target.files[0]; if (!f) return
    const fd = new FormData(); fd.append('file', f)
    try { const r = await api('/api/research/import-csv', { method: 'POST', body: fd }); notify(`Imported ${r.imported_rows} keyword rows (${r.new_niches} new niches discovered)`); reload() }
    catch (x) { notify(x.message, true) }
    e.target.value = ''
  }
  const addEv = async (nid) => {
    try { await api(`/api/niches/${nid}/evidence`, { method: 'POST', body: ev }); setEv({ claim: '', url: '', source_title: '', published: '' }); reload(); notify('Evidence added and opportunities re-scored') }
    catch (x) { notify(x.message, true) }
  }
  const last = runs?.[0]
  return (<div className="col" style={{ gap: 18 }}>
    <div className="row between"><div><h1>Market Research</h1><p className="sub">Niches, keyword evidence, competitors and sources. Every claim is linked and dated.</p></div>
      <div className="row"><label className="btn">Import keyword CSV<input type="file" accept=".csv" hidden onChange={upload} /></label>
        <button className="btn primary" onClick={() => run('/api/research/run', { use_ai: !!status?.credentials.anthropic }, reload)}>Run research now</button></div></div>
    <Err e={err} />
    {last && <div className="card"><h3>Latest run #{last.id} · {new Date(last.started_at).toLocaleString()} ({last.trigger})</h3>
      <div className="small"><b>Sources used:</b> {last.sources.join(' · ')}</div>
      {last.unavailable?.length > 0 && <ul className="small" style={{ color: 'var(--warn)' }}>{last.unavailable.map(u => <li key={u}>{u}</li>)}</ul>}
      <div className="small muted">CSV import accepts exports from keyword tools you subscribe to (eRank, EverBee, Marmalead) or your Etsy stats: columns <code>keyword, searches, competition, ctr, avg_price, niche</code>.</div></div>}
    <div className="card"><table><thead><tr><th>Niche</th><th>Category</th><th>Seasonality</th><th>Evidence</th><th>Live data</th></tr></thead>
      <tbody>{niches?.map(n => <React.Fragment key={n.id}>
        <tr className="click" onClick={() => setOpen(open === n.id ? null : n.id)}>
          <td><b>{n.name}</b>{n.discovered && <> <span className="pill blue">discovered</span></>}<div className="small muted">{n.keywords.slice(0, 4).join(' · ')}</div></td>
          <td>{n.category}</td><td className="small">{n.seasonality}</td><td>{n.evidence.length} sources</td>
          <td>{n.metrics?.competing_listings ? <span className="pill ok">{n.metrics.competing_listings.toLocaleString()} listings</span> : <span className="pill">none</span>}</td></tr>
        {open === n.id && <tr><td colSpan={5}><div className="grid g2">
          <div className="col"><h3>Evidence</h3><ul className="small">{n.evidence.map(e => <li key={e.id}>{e.claim} — {e.url ? <a href={e.url} target="_blank" rel="noreferrer">{e.source_title || 'source'}</a> : e.source_title}
            {' '}<span className="muted">({e.published || 'undated'} · {e.source_type} · retrieved {e.retrieved_at})</span></li>)}</ul>
            <details><summary className="small">Add evidence you found</summary><div className="col" style={{ marginTop: 8 }}>
              <input placeholder="Claim (what the source shows)" value={ev.claim} onChange={e => setEv({ ...ev, claim: e.target.value })} />
              <input placeholder="Source URL" value={ev.url} onChange={e => setEv({ ...ev, url: e.target.value })} />
              <div className="row"><input placeholder="Source title" value={ev.source_title} onChange={e => setEv({ ...ev, source_title: e.target.value })} />
                <input placeholder="YYYY-MM" value={ev.published} onChange={e => setEv({ ...ev, published: e.target.value })} style={{ width: 100 }} />
                <button className="btn sm primary" onClick={() => addEv(n.id)}>Add</button></div></div></details></div>
          <div className="col"><h3>What buyers value</h3><ul className="small">{(n.insights.buyer_values || []).map(x => <li key={x}>{x}</li>)}</ul>
            <h3>Complaints & unmet needs</h3><ul className="small">{(n.insights.gaps || []).map(x => <li key={x}>{x}</li>)}</ul>
            <h3>Design trends</h3><div>{(n.insights.design_trends || []).map(x => <span className="chip" key={x}>{x}</span>)}</div>
            {n.metrics?.competing_listings && <><h3>Live Etsy metrics</h3><div className="small">Median price {money(n.metrics.price_median)} · median favorites {n.metrics.favorites_median} · top tags: {n.metrics.top_tags?.slice(0, 8).join(', ')}</div></>}
            <div className="small muted" style={{ marginTop: 8 }}>Analyst signals: demand {n.analyst.demand ?? '–'} — {n.analyst.demand_rationale}</div></div>
        </div></td></tr>}</React.Fragment>)}</tbody></table></div>
  </div>)
}

// =============================================================== OPPORTUNITIES
export function Opportunities({ id }) {
  const run = useJobRunner()
  const [opps, reload, err] = useLoad(() => api('/api/opportunities?limit=200'))
  const [f, setF] = useState({ niche: '', category: '', minProfit: 0, minComp: 0, minEase: 0, minConf: 0, producible: true, status: 'active', sort: 'score' })
  const [sel, setSel] = useState(id)
  const [cmp, setCmp] = useState([])
  useEffect(() => setSel(id), [id])
  const cats = useMemo(() => [...new Set((opps || []).map(o => o.details.category))], [opps])
  const list = useMemo(() => (opps || []).filter(o =>
    (!f.niche || (o.details.niche + o.concept).toLowerCase().includes(f.niche.toLowerCase())) &&
    (!f.category || o.details.category === f.category) && o.details.profit_per_sale >= f.minProfit &&
    o.factors.competition * 100 >= f.minComp && o.factors.automation * 100 >= f.minEase && o.confidence >= f.minConf &&
    (!f.producible || o.product_type !== 'not_supported_yet') &&
    (f.status === 'all' || (f.status === 'active' ? o.status !== 'dismissed' : o.status === f.status))
  ).sort((a, b) => f.sort === 'score' ? b.score - a.score : f.sort === 'profit' ? b.details.profit_per_sale - a.details.profit_per_sale :
    f.sort === 'confidence' ? b.confidence - a.confidence : b.factors.automation - a.factors.automation).slice(0, 20), [opps, f])
  const setStatus = async (oid, status) => { await api(`/api/opportunities/${oid}`, { method: 'PATCH', body: { status } }); reload() }
  const o = (opps || []).find(x => x.id === sel)
  return (<div className="col" style={{ gap: 18 }}>
    <div><h1>Opportunity Explorer</h1><p className="sub">Top 20 ideas ranked 0–100. The confidence score shows how strong the evidence behind each ranking is.</p></div>
    <Err e={err} />
    <div className="card row">
      <label className="f">Search niche<input value={f.niche} onChange={e => setF({ ...f, niche: e.target.value })} placeholder="e.g. wedding" /></label>
      <label className="f">Category<select value={f.category} onChange={e => setF({ ...f, category: e.target.value })}><option value="">All</option>{cats.map(c => <option key={c}>{c}</option>)}</select></label>
      <label className="f">Min profit/sale ${f.minProfit}<input type="range" min="0" max="25" value={f.minProfit} onChange={e => setF({ ...f, minProfit: +e.target.value })} /></label>
      <label className="f">Low competition ≥ {f.minComp}<input type="range" min="0" max="100" value={f.minComp} onChange={e => setF({ ...f, minComp: +e.target.value })} /></label>
      <label className="f">Ease of production ≥ {f.minEase}<input type="range" min="0" max="100" value={f.minEase} onChange={e => setF({ ...f, minEase: +e.target.value })} /></label>
      <label className="f">Confidence ≥ {f.minConf}<input type="range" min="0" max="100" value={f.minConf} onChange={e => setF({ ...f, minConf: +e.target.value })} /></label>
      <label className="f">Status<select value={f.status} onChange={e => setF({ ...f, status: e.target.value })}><option value="active">Active</option><option value="saved">Saved</option><option value="produced">Produced</option><option value="dismissed">Dismissed</option><option value="all">All</option></select></label>
      <label className="f">Sort<select value={f.sort} onChange={e => setF({ ...f, sort: e.target.value })}><option value="score">Score</option><option value="profit">Profit</option><option value="confidence">Confidence</option><option value="ease">Ease</option></select></label>
      <label className="row small"><input type="checkbox" checked={f.producible} onChange={e => setF({ ...f, producible: e.target.checked })} /> Producible only</label>
      {cmp.length > 1 && <button className="btn" onClick={() => setSel('cmp')}>Compare {cmp.length}</button>}
    </div>
    <div className="card"><table><thead><tr><th></th><th>#</th><th>Opportunity</th><th>Score</th><th>Confidence</th><th>Price</th><th>Profit/sale</th><th>Status</th><th></th></tr></thead>
      <tbody>{list.map((x, i) => <tr key={x.id} className="click" onClick={() => setSel(x.id)}>
        <td onClick={e => e.stopPropagation()}><input type="checkbox" checked={cmp.includes(x.id)} onChange={e => setCmp(e.target.checked ? [...cmp, x.id].slice(-3) : cmp.filter(c => c !== x.id))} /></td>
        <td>{i + 1}</td><td><b>{x.concept}</b><div className="small muted">{x.details.niche}{x.details.discovered ? ' · discovered' : ''}{x.product_type === 'not_supported_yet' ? ' · research only' : ''}</div></td>
        <td><b>{x.score}</b><Bar value={x.score} /></td><td><span className={'pill ' + conf(x.confidence)}>{x.confidence}</span></td>
        <td>{money(x.details.suggested_price)}{x.details.price_range.basis === 'assumption' && <span className="pill warn" title="Assumed price">est</span>}</td>
        <td>{money(x.details.profit_per_sale)}</td><td><Pill k={x.status} /></td>
        <td onClick={e => e.stopPropagation()}>{x.product_type !== 'not_supported_yet' && <button className="btn sm primary" onClick={() => run('/api/products/generate', { opportunity_id: x.id }, (j) => go('studio', j.result?.product_id))}>Generate</button>}</td></tr>)}</tbody></table>
      {!list.length && <div className="empty">No opportunities match these filters.</div>}</div>
    {sel === 'cmp' && <Modal onClose={() => setSel(null)}><h2>Compare</h2><div className={'grid g' + cmp.length}>{cmp.map(cid => { const c = opps.find(z => z.id === cid); return <div key={cid} className="card col">
      <b>{c.concept}</b><Score v={c.score} /><div className="small">Confidence {c.confidence}</div>
      {Object.keys(FACTOR_LABEL).map(k => <div key={k} className="factor"><span>{FACTOR_LABEL[k]}</span><Bar value={c.factors[k] * 100} /><span>{pct(c.factors[k])}</span></div>)}
      <div className="small">Price {money(c.details.suggested_price)} · profit {money(c.details.profit_per_sale)}</div>
      <div className="small">{c.details.pieces}</div></div> })}</div></Modal>}
    {o && <Modal onClose={() => { setSel(null); go('opportunities') }}><OppDetail o={o} onStatus={setStatus} onGenerate={() => run('/api/products/generate', { opportunity_id: o.id }, (j) => go('studio', j.result?.product_id))} /></Modal>}
  </div>)
}

function OppDetail({ o, onStatus, onGenerate }) {
  const d = o.details
  return (<div className="col" style={{ gap: 14 }}>
    <div className="row between"><div><h1>{o.concept}</h1><div className="muted">{d.niche} · {d.product_label} · research date {d.research_date}</div></div>
      <div className="row"><Score v={o.score} label="opportunity" /><Score v={o.confidence} label="evidence confidence" /></div></div>
    <div className="row"><button className="btn" onClick={() => onStatus(o.id, 'saved')}>Save</button><button className="btn" onClick={() => onStatus(o.id, 'dismissed')}>Dismiss</button>
      {o.product_type !== 'not_supported_yet' ? <button className="btn primary" onClick={onGenerate}>Generate Product</button> : <span className="pill warn">Research only — no generator yet</span>}</div>
    <div className="grid g2">
      <div className="card col"><h3>Why it ranks here</h3>{Object.keys(FACTOR_LABEL).map(k => <div key={k}><div className="factor"><span>{FACTOR_LABEL[k]}</span><Bar value={o.factors[k] * 100} /><span>{pct(o.factors[k])}</span></div>
        <div className="small muted" style={{ marginLeft: 148 }}>{d.explanations[k]} <i>({(d.inputs[k] || []).join(', ')})</i></div></div>)}</div>
      <div className="card col"><h3>Business case</h3>
        <div><b>Target customer:</b> {d.target_customer}</div><div><b>Product:</b> {d.pieces}</div>
        <div><b>Recommended style:</b> {d.design_style}</div>
        <div><b>Observed price range:</b> {d.price_range.low != null ? `${money(d.price_range.low)}–${money(d.price_range.high)}` : '—'} <span className={'pill ' + (d.price_range.basis === 'assumption' ? 'warn' : 'ok')}>{d.price_range.basis}</span><div className="small muted">{d.price_range.note}</div></div>
        <div><b>Suggested price:</b> {money(d.suggested_price)} · Etsy fees ≈ {money(d.fees_per_sale)} · production ≈ {money(d.estimated_production_cost)} · <b>profit ≈ {money(d.profit_per_sale)}/sale</b></div>
        <div className="small muted">Fees = $0.20 listing/renewal + 6.5% transaction + 3% + $0.25 processing (US). Offsite Ads (12–15%) optional in Settings.</div>
        {d.live_metrics?.estimated_monthly_sales_per_typical_listing && <div className="notice small">Estimated sales (typical listing): {d.live_metrics.estimated_monthly_sales_per_typical_listing.low}–{d.live_metrics.estimated_monthly_sales_per_typical_listing.high}/month. {d.live_metrics.estimated_monthly_sales_per_typical_listing.method}</div>}
      </div>
      <div className="card col"><h3>Why it's attractive</h3><ul className="small">{d.why_attractive.map(x => <li key={x}>{x}</li>)}</ul>
        <h3>Risk factors</h3><ul className="small">{d.risks.map(x => <li key={x}>{x}</li>)}</ul></div>
      <div className="card col"><h3>Demand evidence</h3><ul className="small">{d.demand_evidence.map(x => <li key={x}>{x}</li>)}</ul>
        <h3>Competition</h3><div className="small">{d.competition_assessment}</div>
        <h3>Keywords</h3><div>{d.keywords.map(k => <span key={k} className="chip">{k}</span>)}</div></div>
      <div className="card col"><h3>Example competitor listings</h3>{d.competitor_urls.length ? <ul className="small">{d.competitor_urls.map(u => <li key={u}><a href={u} target="_blank" rel="noreferrer">{u}</a></li>)}</ul> : <div className="small muted">None collected yet (connect the Etsy API for live examples).</div>}
        <div className="small muted">Used only to understand the market. Designs are never copied.</div></div>
      <div className="card col"><h3>Sources</h3><ul className="small">{d.sources.map(s => <li key={s.url + s.title}><a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a> <span className="muted">({s.published || 'undated'}, {s.type})</span></li>)}</ul>
        <h3>Data not available</h3><ul className="small">{d.confidence_detail.unavailable_data.map(x => <li key={x}>{x}</li>)}</ul>
        <div className="small muted">Confidence: {d.confidence_detail.reasons.join('; ')}</div></div>
    </div></div>)
}

// =============================================================== DESIGN STUDIO
export function Studio({ id }) {
  const [list] = useLoad(() => api('/api/products'))
  const [prod, reload, err] = useLoad(() => id ? api(`/api/products/${id}`) : Promise.resolve(null), [id])
  const run = useJobRunner()
  const { notify, status } = useApp()
  const [big, setBig] = useState(null)
  const [req, setReq] = useState('')
  const [vars, setVars] = useState(null)
  const [tab, setTab] = useState('designs')
  if (!id) return (<div className="col" style={{ gap: 18 }}><div><h1>Design Studio</h1><p className="sub">Pick a product to preview, revise and approve — or generate one from the Opportunity Explorer.</p></div>
    <div className="card"><div className="thumbs">{list?.map(p => <div key={p.id} className="thumb" onClick={() => go('studio', p.id)}><img src={fileUrl(p.hero_preview)} alt="" /><b className="small">{p.name}</b><Pill k={p.status} /></div>)}</div>
      {!list?.length && <div className="empty">No products yet. <a href="#/opportunities">Choose an opportunity</a>.</div>}</div>
    <QuickGenerate /></div>)
  if (!prod) return <Err e={err} />
  const v = prod.versions?.[0] && prod.versions.find(x => x.version === prod.current_version)
  const pieces = v?.files.pieces || []
  const revise = (body) => run(`/api/products/${id}/revise`, body, (j) => { if (j.result?.understood === false) notify(j.result.message, true); if (j.result?.created?.length) notify(`Created matching products #${j.result.created.join(', #')}`); reload() })
  const setStatus = async (s) => { await api(`/api/products/${id}/status`, { method: 'POST', body: { status: s } }); reload(); notify(`Product ${s}`) }
  const suggestions = ['Make this more minimalist', 'Change the colors to sage green and cream', 'Make the typography more elegant', 'Make this suitable for a luxury wedding', 'Create five matching products', 'More white space', 'New layout']
  return (<div className="col" style={{ gap: 16 }}>
    <div className="row between"><div><h1>{prod.name}</h1><div className="row"><Pill k={prod.status} /><span className="muted small">version {prod.current_version} · {prod.product_type}</span></div></div>
      <div className="row"><Score v={v?.qc_score} label="design QC score" />
        <button className="btn danger" onClick={() => setStatus('rejected')}>Reject</button>
        <button className="btn primary" onClick={() => setStatus('approved')}>Approve design</button>
        <button className="btn" onClick={() => go('listing', id)}>Listing →</button></div></div>
    {v?.qc.disclaimer && <div className="notice info small">{v.qc.disclaimer}</div>}
    <div className="tabs">{['designs', 'quality', 'files', 'mockups', 'versions'].map(t => <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>{t[0].toUpperCase() + t.slice(1)}</button>)}</div>
    {tab === 'designs' && <>
      <div className="thumbs">{pieces.map(p => <div key={p.key} className="thumb" onClick={() => setBig(p)}><img src={fileUrl(p.preview) + `?v=${prod.current_version}`} alt={p.label} />
        <div className="row between"><b className="small">{p.label}</b><span className={'pill ' + (p.qc.score >= 90 ? 'ok' : p.qc.score >= 75 ? 'warn' : 'err')}>{p.qc.score}</span></div></div>)}</div>
      <div className="card col"><h3>Request a revision in plain English</h3>
        <div className="row"><input style={{ flex: 1, minWidth: 260 }} value={req} onChange={e => setReq(e.target.value)} placeholder="e.g. Change the colors to dusty blue and ivory" onKeyDown={e => e.key === 'Enter' && req && revise({ request: req })} />
          <button className="btn primary" disabled={!req} onClick={() => revise({ request: req })}>Apply</button>
          <button className="btn" onClick={() => run(`/api/products/${id}/variations`, {}, (j) => setVars(j.result?.variations))}>Show style variations</button></div>
        <div>{suggestions.map(s => <span key={s} className="chip" style={{ cursor: 'pointer' }} onClick={() => setReq(s)}>{s}</span>)}</div>
        <div className="small muted">{status?.revision_help}</div></div>
      {vars && <div className="card"><h3>Variations — click one to apply it</h3><div className="thumbs">{vars.map(x => <div key={x.index} className="thumb" onClick={() => { revise({ params: x.params }); setVars(null) }}>
        <img src={fileUrl(x.preview)} alt="" /><div className="small">{Object.values(x.params).join(' · ')}</div></div>)}</div></div>}
    </>}
    {tab === 'quality' && <div className="grid g2">{pieces.map(p => <div key={p.key} className="card col"><div className="row between"><b>{p.label}</b><span className="score">{p.qc.score}</span></div>
      {p.qc.issues.length ? <ul className="issues small">{p.qc.issues.map((i, k) => <li key={k}><span className={'pill ' + (i.severity === 'error' ? 'err' : i.severity === 'warning' ? 'warn' : '')}>{i.severity}</span> {i.message}</li>)}</ul> : <div className="small" style={{ color: 'var(--ok)' }}>No issues detected by the automated checks.</div>}
      {p.qc.auto_fixes.length > 0 && <div className="small muted">Auto-fixed: {p.qc.auto_fixes.map(a => a.fixed.join('; ')).join(' | ')}</div>}
      <div className="small muted">Balance {p.qc.metrics.h_balance} · ink coverage {Math.round((p.qc.metrics.ink_coverage || 0) * 100)}%</div></div>)}
      <div className="card col"><b>File checks</b>{v.qc.file_checks.length ? <ul className="small">{v.qc.file_checks.map((c, k) => <li key={k}>{c.severity}: {c.message}</li>)}</ul> : <div className="small" style={{ color: 'var(--ok)' }}>All exported files validated (dimensions, DPI, embedded fonts, archives, Etsy limits).</div>}</div></div>}
    {tab === 'files' && <div className="grid g2">
      <div className="card col"><h3>Etsy deliverables (upload these)</h3>{v.files.deliverables.map(d => <div key={d.name} className="row between"><a href={fileUrl(d.path)}>{d.name}</a><span className="small muted">{fmtBytes(d.bytes)}</span></div>)}
        <div className="small muted">Etsy allows 5 files, 20 MB each — packaging respects this automatically.</div>
        <a className="btn" href={fileUrl(v.files.bundle_zip)}>Download complete bundle ({fmtBytes(v.files.bundle_bytes)})</a></div>
      <div className="card col"><h3>All files</h3>{pieces.map(p => <details key={p.key}><summary>{p.label}</summary><ul className="small">{p.files.map(f => <li key={f.name}><a href={fileUrl(f.path)} target="_blank" rel="noreferrer">{f.name}</a> <span className="muted">{f.format.toUpperCase()} · {fmtBytes(f.bytes)} {f.valid ? '✔' : '✖'}</span></li>)}</ul></details>)}
        <div className="small muted">Editable formats: SVG (Inkscape/Illustrator/Affinity/Figma, fonts included) and the browser personalizer (.html). PNG/PDF are print-ready, not editable templates.</div></div></div>}
    {tab === 'mockups' && <div className="thumbs">{v.files.mockups.map(m => <div key={m.name} className="thumb" onClick={() => setBig({ preview: m.path, label: m.caption })}><img src={fileUrl(m.path)} alt="" /><span className="small">{m.caption}</span></div>)}</div>}
    {tab === 'versions' && <div className="card"><table><tbody>{prod.versions.map(x => <tr key={x.version}><td>v{x.version}{x.version === prod.current_version && <> <span className="pill ok">current</span></>}</td>
      <td className="small">{x.revision_note}</td><td>QC {x.qc_score}</td><td className="small muted">{new Date(x.created_at).toLocaleString()}</td>
      <td>{x.version !== prod.current_version && <button className="btn sm" onClick={async () => { await api(`/api/products/${id}/restore/${x.version}`, { method: 'POST' }); reload() }}>Restore</button>}</td></tr>)}</tbody></table></div>}
    {big && <Modal onClose={() => setBig(null)}><h2>{big.label}</h2><img className="preview-big" src={fileUrl(big.preview)} alt="" />
      {big.extra_previews?.length > 0 && <div className="thumbs" style={{ marginTop: 10 }}>{big.extra_previews.map(x => <img key={x} src={fileUrl(x)} alt="" style={{ width: '100%' }} />)}</div>}</Modal>}
  </div>)
}

function QuickGenerate() {
  const { status } = useApp()
  const run = useJobRunner()
  const [t, setT] = useState('wedding_suite')
  return <div className="card row"><b>Or generate directly:</b><select value={t} onChange={e => setT(e.target.value)}>{Object.entries(status?.product_types || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
    <button className="btn primary" onClick={() => run('/api/products/generate', { product_type: t }, (j) => go('studio', j.result?.product_id))}>Generate</button></div>
}

// =============================================================== LIBRARY
export function Library() {
  const [list, reload] = useLoad(() => api('/api/products'))
  const [st, setSt] = useState('')
  const del = async (id) => { if (confirm('Delete this product and its files?')) { await api(`/api/products/${id}`, { method: 'DELETE' }); reload() } }
  return (<div className="col" style={{ gap: 18 }}>
    <div className="row between"><div><h1>Product Library</h1><p className="sub">Completed designs, source files, bundles and previous versions.</p></div>
      <select value={st} onChange={e => setSt(e.target.value)}><option value="">All statuses</option>{['review', 'needs_attention', 'approved', 'published', 'rejected'].map(s => <option key={s}>{s}</option>)}</select></div>
    <div className="grid g3">{list?.filter(p => !st || p.status === st).map(p => <div key={p.id} className="card col">
      <img src={fileUrl(p.hero_preview)} alt="" style={{ width: '100%', height: 220, objectFit: 'contain', background: '#f1eee9', borderRadius: 8 }} />
      <b>{p.name}</b><div className="row"><Pill k={p.status} /><span className="small muted">v{p.current_version} · QC {p.qc_score}</span>{p.listing && <span className="pill">{p.listing.status}</span>}</div>
      <div className="row"><button className="btn sm" onClick={() => go('studio', p.id)}>Open</button><button className="btn sm" onClick={() => go('listing', p.id)}>Listing</button>
        <button className="btn sm danger" onClick={() => del(p.id)}>Delete</button></div></div>)}</div>
    {!list?.length && <div className="empty card">Nothing here yet.</div>}
  </div>)
}

// =============================================================== LISTING STUDIO
export function ListingStudio({ id }) {
  const [list] = useLoad(() => api('/api/products'))
  const [prod, reload] = useLoad(() => id ? api(`/api/products/${id}`) : Promise.resolve(null), [id])
  const { notify, status } = useApp()
  const run = useJobRunner()
  const [l, setL] = useState(null)
  const [tag, setTag] = useState('')
  const [tax, setTax] = useState('')
  useEffect(() => { setL(prod?.listing || null) }, [prod])
  if (!id) return (<div className="col" style={{ gap: 18 }}><div><h1>Listing Studio</h1><p className="sub">Titles, descriptions, tags, prices and mockups for each product.</p></div>
    <div className="card"><table><tbody>{list?.map(p => <tr key={p.id} className="click" onClick={() => go('listing', p.id)}><td><b>{p.name}</b></td><td><Pill k={p.status} /></td><td>{p.listing?.status}</td><td>{money(p.listing?.price)}</td></tr>)}</tbody></table></div></div>)
  if (!l) return <div className="empty">Loading…</div>
  const save = async () => { try { const d = await api(`/api/products/${id}/listing`, { method: 'PUT', body: { title: l.title, description: l.description, tags: l.tags, price: Number(l.price) } }); setL({ ...l, ...d }); notify('Listing saved') } catch (e) { notify(e.message, true) } }
  const approve = async () => { try { await save(); await api(`/api/products/${id}/listing/approve`, { method: 'POST' }); reload(); notify('Listing approved') } catch (e) { notify(e.message, true) } }
  const fee = 0.20 + Number(l.price || 0) * 0.095 + 0.25
  return (<div className="col" style={{ gap: 16 }}>
    <div className="row between"><div><h1>Listing: {prod.name}</h1><div className="row"><Pill k={prod.status} /><span className="pill">{l.status}</span>{l.etsy_listing_id && <span className="pill ok">Etsy draft #{l.etsy_listing_id}</span>}</div></div>
      <div className="row"><button className="btn" onClick={async () => { const d = await api(`/api/products/${id}/listing/regenerate`, { method: 'POST' }); setL({ ...l, ...d }); notify('Regenerated') }}>Regenerate</button>
        <button className="btn" onClick={save}>Save</button><button className="btn primary" onClick={approve}>Approve listing</button></div></div>
    {l.checks?.length > 0 && <div className="notice"><b>Listing checks</b><ul className="small">{l.checks.map((c, i) => <li key={i}>{c.severity}: {c.message}</li>)}</ul></div>}
    <div className="grid g2">
      <div className="card col">
        <label className="f">Title ({l.title.length}/140)<textarea style={{ minHeight: 60 }} value={l.title} onChange={e => setL({ ...l, title: e.target.value })} /></label>
        <label className="f">Tags ({l.tags.length}/13, max 20 characters each)</label>
        <div>{l.tags.map(t => <span key={t} className="chip" style={{ color: t.length > 20 ? 'var(--err)' : undefined }}>{t}<button onClick={() => setL({ ...l, tags: l.tags.filter(x => x !== t) })}>×</button></span>)}</div>
        <div className="row"><input value={tag} maxLength={20} onChange={e => setTag(e.target.value)} placeholder="add tag" /><button className="btn sm" disabled={!tag || l.tags.length >= 13} onClick={() => { setL({ ...l, tags: [...l.tags, tag.toLowerCase()] }); setTag('') }}>Add</button></div>
        <div className="row"><label className="f">Price (USD)<input type="number" step="0.01" value={l.price} onChange={e => setL({ ...l, price: e.target.value })} style={{ width: 120 }} /></label>
          <div className="small">Etsy fees ≈ {money(fee)} · <b>profit ≈ {money(Number(l.price) - fee - (prod.production_cost || 0))}</b><div className="muted">Price basis: {l.price_basis}</div></div></div>
        <div className="small"><b>Category:</b> {l.category}</div>
        <div className="small"><b>Attributes:</b> {Object.entries(l.attributes).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join('/') : v}`).join(' · ')}</div>
        <div className="small"><b>AI disclosure:</b> {l.ai_disclosure}</div>
      </div>
      <div className="card col"><label className="f">Description<textarea style={{ minHeight: 420, fontSize: 13 }} value={l.description} onChange={e => setL({ ...l, description: e.target.value })} /></label></div>
      <div className="card col"><h3>Listing images (mockups + previews)</h3><div className="thumbs">{l.mockups.map(m => <a key={m.name} className="thumb" href={fileUrl(m.path)} target="_blank" rel="noreferrer"><img src={fileUrl(m.path)} alt="" /><span className="small">{m.caption} · {fmtBytes(m.bytes)}</span></a>)}</div></div>
      <div className="card col"><h3>Customer FAQ</h3>{l.faq.map(q => <div key={q.q} className="small"><b>{q.q}</b><div>{q.a}</div></div>)}
        <h3>Files buyers receive</h3><ul className="small">{l.deliverables.map(d => <li key={d.name}>{d.name} ({fmtBytes(d.bytes)})</li>)}</ul></div>
    </div>
    <div className="card row"><b>Publish:</b>
      {status?.credentials.etsy_connected ? <>
        <input placeholder="Etsy taxonomy id" value={tax} onChange={e => setTax(e.target.value)} style={{ width: 160 }} />
        <button className="btn primary" disabled={prod.status !== 'approved' || l.status !== 'approved' || !tax} onClick={() => run(`/api/products/${id}/send-to-etsy`, { taxonomy_id: Number(tax) }, reload)}>Send to Etsy as draft</button>
        <span className="small muted">Creates a DRAFT in your shop — you publish it in Etsy Shop Manager.</span></>
        : <span className="small muted">Connect your Etsy shop in <a href="#/settings">Settings</a> to send approved listings as drafts. Until then, copy the text above and upload the files from the Design Studio “Files” tab.</span>}
    </div>
  </div>)
}

// =============================================================== ANALYTICS
export function Analytics() {
  const [a, reload] = useLoad(() => api('/api/analytics'))
  const { notify } = useApp()
  const up = async (e) => { const fd = new FormData(); fd.append('file', e.target.files[0]); try { const r = await api('/api/analytics/import-sales', { method: 'POST', body: fd }); notify(`Imported ${r.imported} sales rows`); reload() } catch (x) { notify(x.message, true) } }
  if (!a) return null
  return (<div className="col" style={{ gap: 18 }}>
    <div className="row between"><div><h1>Analytics</h1><p className="sub">Research activity, production costs, API spending and real shop performance.</p></div>
      <label className="btn">Import Etsy orders CSV<input type="file" accept=".csv" hidden onChange={up} /></label></div>
    <div className="grid g4">
      <div className="card kpi"><b>{a.research_runs}</b><span>research runs</span></div>
      <div className="card kpi"><b>{money(a.production_cost_total)}</b><span>total production cost</span></div>
      <div className="card kpi"><b>{money(a.budget.month_usd)}</b><span>API spend this month (limit {money(a.budget.monthly_limit_usd)})</span></div>
      <div className="card kpi"><b>{a.sales.orders ? money(a.sales.revenue) : '—'}</b><span>{a.sales.orders ? `${a.sales.orders} items sold (imported)` : 'no sales data yet'}</span></div></div>
    <div className="grid g2">
      <div className="card"><h2>Products by status</h2><table><tbody>{Object.entries(a.products_by_status).map(([k, v]) => <tr key={k}><td><Pill k={k} /></td><td>{v}</td></tr>)}</tbody></table></div>
      <div className="card"><h2>API usage & cost</h2><table><thead><tr><th>Provider</th><th>Calls</th><th>Cost</th></tr></thead><tbody>{a.spend.map(s => <tr key={s.provider}><td>{s.provider}</td><td>{s.calls}</td><td>{money(s.usd)}</td></tr>)}</tbody></table>{!a.spend.length && <div className="small muted">No paid API calls yet.</div>}</div>
      <div className="card"><h2>Shop performance</h2>{a.sales.orders ? <table><tbody>{a.sales.by_item.map(i => <tr key={i.item}><td className="small">{i.item}</td><td>{i.orders}</td><td>{money(i.revenue)}</td></tr>)}</tbody></table>
        : <div className="small muted">Download your sold-orders CSV from Etsy (Shop Manager → Settings → Options → Download Data) and import it here to track real results.</div>}</div>
      <div className="card"><h2>Top opportunity scores</h2><table><tbody>{a.top_scores.map(t => <tr key={t.concept}><td className="small">{t.concept}</td><td>{t.score}</td><td><span className={'pill ' + conf(t.confidence)}>{t.confidence}</span></td></tr>)}</tbody></table></div>
    </div></div>)
}

// =============================================================== SETTINGS
export function Settings() {
  const [s, reload] = useLoad(() => api('/api/settings'))
  const { status, notify, refreshStatus } = useApp()
  const [w, setW] = useState(null)
  useEffect(() => { if (s) setW(s) }, [s])
  if (!w) return null
  const put = async (key) => { try { const r = await api('/api/settings', { method: 'PUT', body: { [key]: w[key] } }); notify(`Saved${r.rescored ? ` · ${r.rescored} opportunities re-scored` : ''}`); reload(); refreshStatus() } catch (e) { notify(e.message, true) } }
  const sumW = Object.values(w.weights).reduce((a, b) => a + Number(b), 0)
  const c = status?.credentials || {}
  const cred = (ok, name, how) => <tr><td><span className={'pill ' + (ok ? 'ok' : '')}>{ok ? 'connected' : 'not set'}</span></td><td><b>{name}</b><div className="small muted">{how}</div></td></tr>
  return (<div className="col" style={{ gap: 18 }}>
    <div><h1>Settings</h1><p className="sub">Scoring weights, spending limits, automation and credentials.</p></div>
    <div className="grid g2">
      <div className="card col"><h2>Opportunity scoring weights</h2>
        {Object.keys(FACTOR_LABEL).map(k => <label key={k} className="factor"><span>{FACTOR_LABEL[k]}</span><input type="range" min="0" max="50" value={w.weights[k]} onChange={e => setW({ ...w, weights: { ...w.weights, [k]: +e.target.value } })} /><span>{w.weights[k]}</span></label>)}
        <div className="small muted">Total {sumW} — weights are normalised automatically.</div><button className="btn primary" onClick={() => put('weights')}>Save & re-score</button></div>
      <div className="card col"><h2>Spending limits</h2>
        <div className="row"><label className="f">Daily limit (USD)<input type="number" step="0.5" value={w.budget.daily_usd} onChange={e => setW({ ...w, budget: { ...w.budget, daily_usd: +e.target.value } })} /></label>
          <label className="f">Monthly limit (USD)<input type="number" step="1" value={w.budget.monthly_usd} onChange={e => setW({ ...w, budget: { ...w.budget, monthly_usd: +e.target.value } })} /></label></div>
        <div className="row"><label className="f">Cost per AI image (USD)<input type="number" step="0.01" value={w.budget.image_cost_usd} onChange={e => setW({ ...w, budget: { ...w.budget, image_cost_usd: +e.target.value } })} /></label>
          <label className="f">Max AI images per product<input type="number" value={w.budget.max_images_per_product} onChange={e => setW({ ...w, budget: { ...w.budget, max_images_per_product: +e.target.value } })} /></label></div>
        <div className="small muted">Paid calls are blocked before they would exceed a limit. Today: {money(status?.budget.today_usd)} · this month: {money(status?.budget.month_usd)}</div>
        <button className="btn primary" onClick={() => put('budget')}>Save limits</button></div>
      <div className="card col"><h2>Scheduled research</h2>
        <label className="row"><input type="checkbox" checked={w.schedule.enabled} onChange={e => setW({ ...w, schedule: { ...w.schedule, enabled: e.target.checked } })} /> Run research every day</label>
        <div className="row"><label className="f">Hour (0-23)<input type="number" min="0" max="23" value={w.schedule.hour} onChange={e => setW({ ...w, schedule: { ...w.schedule, hour: +e.target.value } })} /></label>
          <label className="f">Minute<input type="number" min="0" max="59" value={w.schedule.minute} onChange={e => setW({ ...w, schedule: { ...w.schedule, minute: +e.target.value } })} /></label>
          <label className="f">Recommend top<input type="number" min="1" max="20" value={w.schedule.top_n} onChange={e => setW({ ...w, schedule: { ...w.schedule, top_n: +e.target.value } })} /></label></div>
        <label className="row"><input type="checkbox" checked={w.schedule.auto_generate_drafts} onChange={e => setW({ ...w, schedule: { ...w.schedule, auto_generate_drafts: e.target.checked } })} /> Also generate draft products (max <input type="number" min="0" max="10" value={w.schedule.max_drafts_per_run} style={{ width: 60 }} onChange={e => setW({ ...w, schedule: { ...w.schedule, max_drafts_per_run: +e.target.value } })} /> per day)</label>
        <div className="small muted">Nothing is ever published automatically. Drafts wait for your review; duplicates are skipped. The app must be running at the scheduled time.</div>
        <button className="btn primary" onClick={() => put('schedule')}>Save schedule</button></div>
      <div className="card col"><h2>Shop & quality</h2>
        <label className="f">Shop name<input value={w.shop.shop_name} onChange={e => setW({ ...w, shop: { ...w.shop, shop_name: e.target.value } })} /></label>
        <label className="row"><input type="checkbox" checked={w.shop.include_offsite_ads} onChange={e => setW({ ...w, shop: { ...w.shop, include_offsite_ads: e.target.checked } })} /> Include Offsite Ads fee ({Math.round(w.shop.offsite_ads_rate * 100)}%) in profit estimates</label>
        <button className="btn" onClick={() => put('shop')}>Save shop</button>
        <label className="f">Minimum QC score for “ready for review”<input type="number" value={w.quality.min_qc_score} onChange={e => setW({ ...w, quality: { ...w.quality, min_qc_score: +e.target.value } })} /></label>
        <button className="btn" onClick={() => put('quality')}>Save quality</button></div>
    </div>
    <div className="card"><h2>Credentials</h2><p className="small muted">Keys live in the <code>.env</code> file in the app folder (never in code). Restart the app after editing it. See README for step-by-step instructions.</p>
      <table><tbody>
        {cred(c.etsy_api_key, 'Etsy Open API key (ETSY_API_KEY + ETSY_SHARED_SECRET)', 'Live listing counts, prices, favorites, views, tags. Free: etsy.com/developers → Create a New App.')}
        {cred(c.etsy_connected, 'Etsy shop connection (OAuth)', 'Lets the app create DRAFT listings in your shop.')}
        {cred(c.openai_images, 'OpenAI image generation (OPENAI_API_KEY)', 'Optional AI artwork. Spend-limited.')}
        {cred(c.anthropic, 'Anthropic API (ANTHROPIC_API_KEY)', 'Optional: AI web research for new niches + free-form revision requests.')}
        {cred(c.canva, 'Canva Connect (CANVA_CLIENT_ID / SECRET)', 'Optional: import PDFs into Canva as editable designs.')}
      </tbody></table>
      <div className="row" style={{ marginTop: 10 }}>{c.etsy_api_key && <a className="btn" href="/api/etsy/oauth/start">Connect Etsy shop</a>}{c.canva && <a className="btn" href="/api/canva/oauth/start">Connect Canva</a>}</div></div>
  </div>)
}
