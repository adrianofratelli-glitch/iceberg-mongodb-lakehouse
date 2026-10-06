// O prazo cobre headers e corpo; nenhuma escrita é reenviada automaticamente.
async function boundedRequest(work, timeoutMs = 30000) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try { return await work(controller.signal) }
  finally { clearTimeout(timer) }
}

const json = async (res) => {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    // FastAPI validation errors come as a list of {msg}; show text, not [object Object].
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d) => d.msg).filter(Boolean).join('; ')
      : body.detail
    throw new Error(detail || `HTTP ${res.status}`)
  }
  return res.json()
}

const request = (path, options) => boundedRequest(
  async signal => json(await fetch(path, { ...options, signal })),
  path === '/preflight' ? 30000 : 300000,
)

export const api = {
  preflight: () => request('/preflight'),
  visaoGeral: () => request('/api/visao-geral'),
  schema: () => request('/api/schema'),
  pedido: (id) => request(`/api/pedido/${id}`),
  demo: (op) => request(`/api/demo/${op}`, { method: 'POST' }),
  corrigirPostImages: () => request('/api/corrigir/post-images', { method: 'POST' }),
  snapshots: () => request('/api/snapshots'),
  pedidoNoSnapshot: (snapshotId, orderId) =>
    request(`/api/snapshots/${snapshotId}/pedido/${orderId}`),
  consultas: () => request('/api/consultas'),
  rodarConsulta: (id) => request(`/api/consultas/${id}`, { method: 'POST' }),
  lag: () => request('/api/lag'),
}

export const fmtInt = (n) =>
  typeof n === 'number' ? n.toLocaleString('pt-BR') : n ?? '—'

export const fmtBRL = (n) =>
  typeof n === 'number'
    ? n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 })
    : '—'

export const fmtBytes = (n) => {
  if (typeof n !== 'number') return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
