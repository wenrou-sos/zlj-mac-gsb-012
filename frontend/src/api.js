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
  // 标签与校验
  validate: (payload, packageId) =>
    request('/validate' + (packageId ? `?package_id=${packageId}` : ''), {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  list: () => request('/labels'),
  create: (payload) => request('/labels', { method: 'POST', body: JSON.stringify(payload) }),
  update: (id, payload) => request(`/labels/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  remove: (id) => request(`/labels/${id}`, { method: 'DELETE' }),
  validateSaved: (id) => request(`/labels/${id}/validate`),
  labelValidations: (id) => request(`/labels/${id}/validations`),

  // 规则包
  ruleDefinitions: () => request('/rule-definitions'),
  listPackages: () => request('/rule-packages'),
  getPackage: (id) => request(`/rule-packages/${id}`),
  createPackage: (payload) =>
    request('/rule-packages', { method: 'POST', body: JSON.stringify(payload) }),
  updatePackage: (id, payload) =>
    request(`/rule-packages/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  publishPackage: (id, effectiveDate) =>
    request(`/rule-packages/${id}/publish`, {
      method: 'POST',
      body: JSON.stringify({ effective_date: effectiveDate }),
    }),
  deletePackage: (id) => request(`/rule-packages/${id}`, { method: 'DELETE' }),
  recheck: (id) => request(`/rule-packages/${id}/recheck`, { method: 'POST' }),

  // 重检任务
  listRecheckJobs: () => request('/recheck-jobs'),
  getRecheckJob: (id) => request(`/recheck-jobs/${id}`),
}
