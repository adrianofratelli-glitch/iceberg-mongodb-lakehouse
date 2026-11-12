// Faixa de modo da demo, a partir do /preflight (modo + resumo do backend).
// Só aparece quando a demo não está completa; `completo` e respostas antigas
// (sem `modo`) não mostram nada. Se o card do Iceberg já mostra o AvisoAws
// (que diz que a credencial caiu e que o lado MongoDB segue), a faixa de
// somente MongoDB repetiria a mesma coisa e fica escondida.
export function avisoDeModo(preflight, { avisoAwsVisivel = false } = {}) {
  const modo = preflight?.modo
  if (!modo || modo === 'completo' || !preflight.resumo) return null
  if (modo === 'somente_mongodb' && avisoAwsVisivel) return null
  return {
    classe: modo === 'com_falha' ? 'bad' : 'warn',
    titulo: modo === 'somente_mongodb' ? 'Modo somente MongoDB.' : 'Demo com falha.',
    texto: preflight.resumo.replace(/^Modo somente MongoDB:\s*/, ''),
  }
}
