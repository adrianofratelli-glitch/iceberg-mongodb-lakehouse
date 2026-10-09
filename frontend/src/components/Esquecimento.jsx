import { useState } from 'react'
import { api } from '../api'
import AvisoAws from './AvisoAws'

const PEDIDO = 'PED-AOVIVO-001'

// O DELETE tira a linha da visão atual, não do histórico: os snapshots
// anteriores ainda referenciam o arquivo de dados (é o time travel). Este
// painel mostra os passos que faltam para o apagamento definitivo e verifica,
// snapshot a snapshot, se o pedido ainda pode voltar.
export default function Esquecimento() {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)
  const [ocupado, setOcupado] = useState(null)

  const verificar = async () => {
    setOcupado('verificar')
    setErro(null)
    try {
      setDados(await api.esquecimento(PEDIDO))
    } catch (e) {
      setErro(e.message)
    } finally {
      setOcupado(null)
    }
  }

  const expurgar = async () => {
    setOcupado('expurgar')
    setErro(null)
    try {
      const r = await api.expurgar(PEDIDO)
      setDados((d) => ({ ...(d || {}), ...r }))
    } catch (e) {
      setErro(e.message)
    } finally {
      setOcupado(null)
    }
  }

  const passos = dados?.passos
  const pendente = dados?.disponivel && !dados?.apagado_do_lake

  return (
    <>
      <p className="hint" style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
        O DELETE tira o pedido da visão atual do Iceberg, mas os snapshots anteriores
        continuam com ele — é isso que permite o time travel. Apagar de vez exige
        reescrever os arquivos (OPTIMIZE) e expirar os snapshots (VACUUM).
      </p>

      <div className="actions">
        <button onClick={verificar} disabled={Boolean(ocupado)}>
          {ocupado === 'verificar' ? 'Verificando…' : `Verificar ${PEDIDO} nos snapshots`}
        </button>
        {dados && (
          <button
            className="ghost"
            onClick={expurgar}
            disabled={Boolean(ocupado) || !dados.expurgo_habilitado || dados.no_mongo || !pendente}
            title={dados.expurgo_habilitado ? 'OPTIMIZE + VACUUM no Athena' : 'Desligado: ALLOW_LAKE_PURGE=1 no backend'}
          >
            {ocupado === 'expurgar' ? 'Expurgando…' : 'Expurgar do histórico'}
          </button>
        )}
      </div>

      {erro && <div className="notice bad"><strong>Falhou.</strong> {erro}</div>}

      {dados && (
        <>
          {dados.no_mongo && (
            <div className="notice warn" role="status">
              O pedido ainda existe no MongoDB. Rode o DELETE no ciclo CDC primeiro.
            </div>
          )}
          {dados.erro && <AvisoAws erro={dados.erro} />}
          {dados.disponivel && !dados.erro && (
            <div className={`notice ${dados.apagado_do_lake ? 'ok' : 'warn'}`} role="status">
              {dados.apagado_do_lake ? (
                <><strong>Nenhum snapshot retido devolve o pedido</strong> ({dados.snapshots_verificados} verificados).</>
              ) : (
                <>
                  <strong>O pedido ainda pode voltar.</strong>{' '}
                  Visão atual: {dados.linhas_na_visao_atual} linha(s); aparece em{' '}
                  {dados.snapshots_com_pedido?.length ?? 0} de {dados.snapshots_verificados} snapshot(s).
                </>
              )}
            </div>
          )}
          {!dados.expurgo_habilitado && (
            <p className="empty">
              Expurgo desligado nesta instância (apaga o time travel da tabela inteira).
              Para habilitar: <code>ALLOW_LAKE_PURGE=1</code> no backend, ou rode{' '}
              <code>stream-processing/forget_order.py --purge</code>.
            </p>
          )}

          {passos && (
            <ol className="rtbf-steps">
              {passos.map((p) => (
                <li key={p.passo}>
                  <strong>{p.passo}</strong> — {p.descricao}
                  {p.sql && (
                    <pre className="mono">{p.sql.join(';\n')}</pre>
                  )}
                </li>
              ))}
            </ol>
          )}

          {dados.ressalvas?.length > 0 && (
            <ul className="rtbf-notes">
              {dados.ressalvas.map((r) => <li key={r}>{r}</li>)}
            </ul>
          )}
        </>
      )}
    </>
  )
}
