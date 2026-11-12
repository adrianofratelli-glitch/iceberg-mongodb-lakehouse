// Faixa de modo da demo, a partir do /preflight (modo + resumo do backend).
// Só aparece quando a demo não está completa; `completo` e respostas antigas
// (sem `modo`) não mostram nada.
export function avisoDeModo(preflight) {
  const modo = preflight?.modo
  if (!modo || modo === 'completo' || !preflight.resumo) return null
  return {
    classe: modo === 'com_falha' ? 'bad' : 'warn',
    titulo: modo === 'somente_mongodb' ? 'Modo somente MongoDB.' : 'Demo com falha.',
    texto: preflight.resumo.replace(/^Modo somente MongoDB:\s*/, ''),
  }
}
