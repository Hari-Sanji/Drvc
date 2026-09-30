// Thin fetch wrapper: attaches the bearer token, normalizes errors into readable messages.
const store = {
  get() {
    try { return localStorage.getItem('drcv-token') || sessionStorage.getItem('drcv-token') } catch { return null }
  },
  set(token, remember) {
    try {
      localStorage.removeItem('drcv-token'); sessionStorage.removeItem('drcv-token')
      if (token) (remember ? localStorage : sessionStorage).setItem('drcv-token', token)
    } catch { /* storage unavailable: keep in memory */ }
    memToken = token
  },
}
let memToken = null
let onUnauthorized = () => {}
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }
export const getToken = () => store.get() || memToken
export const setToken = (t, remember) => store.set(t, remember)

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status }
}

async function request(method, path, body, opts = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload = body
  if (body && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  let res
  try {
    res = await fetch(`/api${path}`, { method, headers, body: payload, signal: opts.signal })
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new ApiError('Unable to reach the server. Check that the backend is running.', 0)
  }
  if (res.status === 401 && !path.startsWith('/auth/login')) onUnauthorized()
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try { const j = await res.json(); if (j.detail) msg = typeof j.detail === 'string' ? j.detail : msg } catch { /* ignore */ }
    throw new ApiError(msg, res.status)
  }
  if (opts.raw) return res
  const ct = res.headers.get('content-type') || ''
  return ct.includes('application/json') ? res.json() : res.text()
}

export const api = {
  get: (p, o) => request('GET', p, undefined, o),
  post: (p, b, o) => request('POST', p, b, o),
  put: (p, b) => request('PUT', p, b),
  patch: (p, b) => request('PATCH', p, b),
  del: (p) => request('DELETE', p),
  blob: async (p) => (await request('GET', p, undefined, { raw: true })).blob(),
}

// Upload with progress (fetch has no upload progress events).
export function uploadFiles(caseId, files, onProgress) {
  return new Promise((resolve, reject) => {
    const fd = new FormData()
    files.forEach((f) => fd.append('files', f, f.name))
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `/api/cases/${caseId}/records`)
    const t = getToken()
    if (t) xhr.setRequestHeader('Authorization', `Bearer ${t}`)
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress?.(e.loaded / e.total) }
    xhr.onload = () => {
      let j = null
      try { j = JSON.parse(xhr.responseText) } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(j)
      else reject(new ApiError(j?.detail || 'Unable to process this file. Please verify the file type and try again.', xhr.status))
    }
    xhr.onerror = () => reject(new ApiError('Upload failed: the server could not be reached.', 0))
    xhr.send(fd)
  })
}

export async function downloadFile(path, filename) {
  const blob = await api.blob(path)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}
