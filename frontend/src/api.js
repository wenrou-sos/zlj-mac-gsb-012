const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `请求失败 (${res.status})`)
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  validate: (payload) => request('/validate', { method: 'POST', body: JSON.stringify(payload) }),
  list: () => request('/labels'),
  create: (payload) => request('/labels', { method: 'POST', body: JSON.stringify(payload) }),
  update: (id, payload) => request(`/labels/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  remove: (id) => request(`/labels/${id}`, { method: 'DELETE' }),
}
