const json = async (res) => {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  preflight: () => fetch('/preflight').then(json),
  visaoGeral: () => fetch('/api/visao-geral').then(json),
  schema: () => fetch('/api/schema').then(json),
  pedido: (id) => fetch(`/api/pedido/${id}`).then(json),
  demo: (op) => fetch(`/api/demo/${op}`, { method: 'POST' }).then(json),
  corrigirPostImages: () => fetch('/api/corrigir/post-images', { method: 'POST' }).then(json),
  snapshots: () => fetch('/api/snapshots').then(json),
  pedidoNoSnapshot: (snapshotId, orderId) =>
    fetch(`/api/snapshots/${snapshotId}/pedido/${orderId}`).then(json),
  consultas: () => fetch('/api/consultas').then(json),
  rodarConsulta: (id) => fetch(`/api/consultas/${id}`, { method: 'POST' }).then(json),
  lag: () => fetch('/api/lag').then(json),
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
