import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import AvisoAws from './AvisoAws'
import QueryDetails from './QueryDetails'

const PASSOS = [
  { op: 'insert', rotulo: 'INSERT', descricao: 'Pedido novo entra pelo caminho transacional.' },
  { op: 'update', rotulo: 'UPDATE', descricao: 'Data lake append-only não faria isso sem reescrever partição.' },
  { op: 'delete', rotulo: 'DELETE', descricao: 'A linha some do lake. Direito ao esquecimento atravessa o circuito.' },
  { op: 'schema', rotulo: 'CAMPO NOVO', descricao: 'fraudScore vira coluna sem ALTER TABLE.' },
]

const PEDIDO = 'PED-AOVIVO-001'
const PEDIDO_SCHEMA = 'PED-AOVIVO-002'

export default function CicloCdc({ aoMudar }) {
  const [ocupado, setOcupado] = useState(null)
  const [mensagem, setMensagem] = useState(null)
  const [erro, setErro] = useState(null)
  const [mongo, setMongo] = useState(null)
  const [iceberg, setIceberg] = useState(null)
  const [decorrido, setDecorrido] = useState(null)
  const [propagou, setPropagou] = useState(null)
  const [queryDetails, setQueryDetails] = useState(null)
  const cancelar = useRef(false)

  useEffect(() => () => { cancelar.current = true }, [])

  const alvo = (op) => (op === 'schema' ? PEDIDO_SCHEMA : PEDIDO)

  const esperarPropagacao = async (op) => {
    const inicio = Date.now()
    const esperado = op === 'delete' ? 0 : 1
    for (let tentativa = 0; tentativa < 40; tentativa += 1) {
      if (cancelar.current) return
      await new Promise((r) => setTimeout(r, 3000))
      setDecorrido(Math.round((Date.now() - inicio) / 1000))
      try {
        const dados = await api.pedido(alvo(op))
        setMongo(dados.mongo)
        setIceberg(dados.iceberg)
        if (dados.iceberg?.erro) return
        const linhas = dados.iceberg?.linhas?.length ?? 0
        const status = dados.iceberg?.linhas?.[0]?.[1]
        const bate =
          op === 'delete'
            ? linhas === esperado
            : linhas === esperado && (op !== 'update' || status === 'EM_TRANSPORTE')
        if (bate) {
          setPropagou(Math.round((Date.now() - inicio) / 1000))
          aoMudar?.()
          return
        }
      } catch (e) {
        setErro(e.message)
        return
      }
    }
    setPropagou(null)
  }

  const executar = async (op) => {
    setOcupado(op)
    setErro(null)
    setPropagou(null)
    setDecorrido(0)
    setIceberg(null)
    try {
      const resposta = await api.demo(op)
      setMensagem(resposta.mensagem)
      setMongo(resposta.documento)
      setQueryDetails(resposta.query_details)
      aoMudar?.()
      await esperarPropagacao(op)
    } catch (e) {
      setErro(e.message)
    } finally {
      setOcupado(null)
    }
  }

  const resetar = async () => {
    setOcupado('reset')
    try {
      const r = await api.demo('reset')
      setMensagem(r.mensagem)
      setMongo(null)
      setIceberg(null)
      setPropagou(null)
      setDecorrido(null)
      setQueryDetails(r.query_details)
      aoMudar?.()
    } catch (e) {
      setErro(e.message)
    } finally {
      setOcupado(null)
    }
  }

  return (
    <>
      <div className="actions">
        {PASSOS.map((passo) => (
          <button
            key={passo.op}
            className={passo.op === 'insert' ? 'primary' : ''}
            onClick={() => executar(passo.op)}
            disabled={Boolean(ocupado)}
            title={passo.descricao}
          >
            {ocupado === passo.op ? `${passo.rotulo}…` : passo.rotulo}
          </button>
        ))}
        <button className="ghost" onClick={resetar} disabled={Boolean(ocupado)}>
          Limpar
        </button>
      </div>

      {mensagem && !erro && <div className="notice ok">{mensagem}</div>}
      {erro && <div className="notice bad"><strong>Falhou.</strong> {erro}</div>}
      {queryDetails && (
        <QueryDetails
          operation={queryDetails.operation}
          namespace={queryDetails.namespace}
          query={queryDetails.query}
          explain={queryDetails.explain}
        />
      )}

      {(mongo || iceberg) && (
        <div className="timeline">
          <div className="step done">
            <span className="badge">MONGODB</span>
            <span>
              {mongo
                ? `${mongo._id ?? '—'} · ${mongo.status ?? '—'} · R$ ${mongo.amount ?? '—'}`
                : 'documento removido'}
            </span>
          </div>
          <div className={`step ${propagou !== null ? 'done' : 'wait'}`}>
            <span className="badge">ICEBERG</span>
            <span>
              {iceberg?.erro
                ? 'indisponível'
                : propagou !== null
                  ? `refletido em ${propagou}s`
                  : `aguardando propagação… ${decorrido ?? 0}s`}
            </span>
          </div>
        </div>
      )}

      {iceberg?.erro && <AvisoAws erro={iceberg.erro} />}

      {iceberg && !iceberg.erro && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>{(iceberg.colunas || []).map((c) => <th key={c}>{c}</th>)}</tr>
            </thead>
            <tbody>
              {(iceberg.linhas || []).map((linha, i) => (
                <tr key={i}>{linha.map((c, j) => <td key={j}>{c === '' ? '—' : c}</td>)}</tr>
              ))}
              {!(iceberg.linhas || []).length && (
                <tr><td colSpan={(iceberg.colunas || []).length || 1}>0 linhas — o delete propagou.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
