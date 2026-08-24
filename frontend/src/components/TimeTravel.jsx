import { useEffect, useState } from 'react'
import { api, fmtBytes } from '../api'
import AvisoAws from './AvisoAws'
import Tabela from './Tabela'

export default function TimeTravel() {
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState(null)
  const [selecionada, setSelecionada] = useState(null)
  const [versao, setVersao] = useState(null)
  const [carregando, setCarregando] = useState(false)

  const carregar = () => {
    setCarregando(true)
    api.snapshots()
      .then((r) => (r.disponivel ? setDados(r) : setErro(r.erro)))
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false))
  }

  useEffect(carregar, [])

  const consultar = async (linha, indice) => {
    setSelecionada(indice)
    setVersao({ carregando: true })
    try {
      const r = await api.pedidoNoSnapshot(linha[0], 'PED-AOVIVO-001')
      setVersao(r.disponivel ? r : { erro: r.erro })
    } catch (e) {
      setVersao({ erro: e.message })
    }
  }

  if (erro) return <AvisoAws erro={erro} />

  return (
    <>
      <p className="hint" style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
        Cada commit do processor virou um snapshot. Clique em um para ver o pedido
        como ele estava naquele instante — inclusive depois de apagado.
      </p>

      {carregando && !dados && <p className="empty">Consultando o catálogo…</p>}

      {dados && (
        <>
          <Tabela
            colunas={dados.colunas}
            linhas={dados.linhas}
            selecionada={selecionada}
            aoClicar={consultar}
          />
          <p className="empty">
            {dados.tempo_ms} ms · {fmtBytes(dados.bytes_escaneados)} escaneados
          </p>
        </>
      )}

      {versao?.carregando && <p className="empty">Viajando no tempo…</p>}
      {versao?.erro && <AvisoAws erro={versao.erro} />}
      {versao && !versao.carregando && !versao.erro && (
        <div className="notice ok">
          {versao.linhas?.length ? (
            <>
              <strong>Nesse snapshot o pedido existia:</strong>{' '}
              <span className="mono">
                {versao.linhas[0][0]} · {versao.linhas[0][1]} · R$ {versao.linhas[0][2]}
              </span>
            </>
          ) : (
            <><strong>Nesse snapshot o pedido não existia</strong> — anterior ao insert, ou posterior ao delete.</>
          )}
        </div>
      )}
    </>
  )
}
