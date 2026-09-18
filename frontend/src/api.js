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
  // 标签
  validate: (payload, packageId = null) =>
    request(`/validate${packageId ? `?package_id=${packageId}` : ''}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  list: () => request('/labels'),
  create: (payload) => request('/labels', { method: 'POST', body: JSON.stringify(payload) }),
  update: (id, payload) => request(`/labels/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  remove: (id) => request(`/labels/${id}`, { method: 'DELETE' }),
  validations: (id) => request(`/labels/${id}/validations`),

  // 规则目录
  ruleCatalog: () => request('/rule-catalog'),

  // 规则包
  packages: (status) => request(`/rule-packages${status ? `?status=${status}` : ''}`),
  effectivePackage: () => request('/rule-packages/effective'),
  package: (id) => request(`/rule-packages/${id}`),
  createDraft: (payload) =>
    request('/rule-packages/draft', { method: 'POST', body: JSON.stringify(payload) }),
  updatePackage: (id, payload) =>
    request(`/rule-packages/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  patchRule: (id, code, patch) =>
    request(`/rule-packages/${id}/rules/${code}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  publishPackage: (id, effectiveDate = null) =>
    request(`/rule-packages/${id}/publish`, {
      method: 'POST',
      body: JSON.stringify(effectiveDate ? { effective_date: effectiveDate } : {}),
    }),
  archivePackage: (id) => request(`/rule-packages/${id}/archive`, { method: 'POST' }),
  deletePackage: (id) => request(`/rule-packages/${id}`, { method: 'DELETE' }),

  // 批量重检
  createRecheck: (payload) => request('/rechecks', { method: 'POST', body: JSON.stringify(payload) }),
  rechecks: () => request('/rechecks'),
  recheck: (id) => request(`/rechecks/${id}`),
}
