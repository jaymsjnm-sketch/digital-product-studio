export async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', headers: {} }
  if (opts.body instanceof FormData) init.body = opts.body
  else if (opts.body !== undefined) { init.body = JSON.stringify(opts.body); init.headers['Content-Type'] = 'application/json' }
  const r = await fetch(path, init)
  const txt = await r.text()
  let data = null
  try { data = txt ? JSON.parse(txt) : null } catch { data = txt }
  if (!r.ok) throw new Error((data && data.detail) || `Request failed (${r.status})`)
  return data
}
export const fileUrl = (p) => (p ? `/files/${p}` : '')
export const money = (v) => (v === null || v === undefined ? '—' : `$${Number(v).toFixed(2)}`)
export const pct = (v) => `${Math.round((v || 0) * 100)}`
export const fmtBytes = (b) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`)
