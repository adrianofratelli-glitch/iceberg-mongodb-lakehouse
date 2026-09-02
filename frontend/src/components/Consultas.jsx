import { useEffect, useState } from 'react'
import { api, fmtBytes } from '../api'
import AvisoAws from './AvisoAws'
import Tabela from './Tabela'
import QueryDetails from './QueryDetails'

export default function Consultas() {
  const [lista, setLista] = useState([])
  const [ativa, setAtiva] = useState(null)
  const [resultado, setResultado] = useState(null)
  const [carregando, setCarregando] = useState(false)

  useEffect(() => {
    api.consultas().then((r) => setLista(r.consultas)).catch(() => setLista([]))
  }, [])

  const rodar = async (id) => {
    setAtiva(id)
    setCarregando(true)
    setResultado(null)
    try {
      const r = await api.rodarConsulta(id)
      setResultado(r)
    } catch (e) {
      setResultado({ erro: e.message })
    } finally {
      setCarregando(false)
    }
  }

  return (
    <>
      <div className="actions">
        {lista.map((c) => (
          <button
            key={c.id}
            className={ativa === c.id ? 'primary tiny' : 'tiny'}
            onClick={() => rodar(c.id)}
            disabled={carregando}
            title={c.titulo}
          >
            {c.id.replace(/^\d+_/, '').replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {carregando && <p className="empty">Rodando no Athena…</p>}

      {resultado?.erro && <AvisoAws erro={resultado.erro} />}
      {resultado && resultado.disponivel === false && <AvisoAws erro={resultado.erro} />}

      {resultado?.colunas && (
        <>
          <Tabela colunas={resultado.colunas} linhas={resultado.linhas} />
          <p className="empty">
            {resultado.tempo_ms} ms · {fmtBytes(resultado.bytes_escaneados)} escaneados ·
            {' '}sem nenhum impacto no cluster operacional
          </p>
        </>
      )}
      {resultado?.sql && (
        <QueryDetails
          operation="Athena StartQueryExecution"
          namespace="Iceberg catalog"
          query={resultado.sql}
          explain={{
            tempo_ms: resultado.tempo_ms,
            bytes_escaneados: resultado.bytes_escaneados,
            observacao: 'A métrica de bytes escaneados é o sinal de custo relevante no Athena.',
          }}
        />
      )}
    </>
  )
}
