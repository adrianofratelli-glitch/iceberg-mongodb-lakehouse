import { useCallback, useEffect, useState } from 'react'
import { api, fmtBRL, fmtBytes, fmtInt } from './api'
import AvisoAws from './components/AvisoAws'
import CicloCdc from './components/CicloCdc'
import Consultas from './components/Consultas'
import TimeTravel from './components/TimeTravel'

export default function App() {
  const [visao, setVisao] = useState(null)
  const [schema, setSchema] = useState(null)
  const [preflight, setPreflight] = useState(null)
  const [erro, setErro] = useState(null)

  const carregar = useCallback(() => {
    api.visaoGeral().then(setVisao).catch((e) => setErro(e.message))
    api.schema().then(setSchema).catch(() => setSchema(null))
  }, [])

  useEffect(() => {
    carregar()
    api.preflight().then(setPreflight).catch(() => setPreflight(null))
  }, [carregar])

  const mongo = visao?.mongo
  const iceberg = visao?.iceberg
  const aws = preflight?.checks?.find((c) => c.item === 'Credencial AWS')
  const postImages = preflight?.checks?.find((c) => c.item === 'changeStreamPreAndPostImages')

  // Duas divergências diferentes: tabela duplicada (total > ids) e propagação
  // pendente (contagens diferentes, mas sem duplicata). Dizer "duplicada" na
  // segunda é alarme falso — é só o CDC ainda a caminho.
  const duplicada =
    iceberg?.disponivel && iceberg.total > iceberg.distintos
  const propagando =
    iceberg?.disponivel && !duplicada && iceberg.total !== mongo?.total

  const estado = !visao
    ? { classe: '', texto: 'carregando' }
    : visao.convergiu
      ? { classe: 'ok', texto: 'convergido' }
      : duplicada
        ? { classe: 'bad', texto: 'tabela duplicada' }
        : propagando
          ? { classe: 'warn', texto: 'propagando' }
          : iceberg?.disponivel
            ? { classe: 'warn', texto: 'divergente' }
            : { classe: 'warn', texto: 'iceberg offline' }

  return (
    <div data-pov-shell>
      <a className="pov-skip-link" href="#conteudo-principal">Pular para o conteúdo</a>

      <header className="topbar">
        <div className="brand">
          <span className="leaf" aria-hidden="true">◆</span>
          <span>Iceberg + MongoDB</span>
        </div>
        <div className="spacer" />
        <span className={`pill ${estado.classe}`}>
          <span className="dot" aria-hidden="true" />
          {estado.texto}
        </span>
      </header>

      <main id="conteudo-principal">
        <div className="hero">
          <p className="eyebrow">Lakehouse · Change data capture</p>
          <h1>Uma coleção operacional que também é <em>tabela Iceberg</em>.</h1>
          <p>
            Insert, update, delete e campo novo saem do MongoDB e chegam a uma tabela
            Apache Iceberg no S3, consultável por Athena. Sem ETL, sem Spark, sem
            Debezium. As duas metades abaixo deveriam mostrar o mesmo número.
          </p>
        </div>

        {erro && <div className="notice bad"><strong>Backend indisponível.</strong> {erro}</div>}

        {postImages?.estado === 'falha' && (
          <div className="notice warn">
            <strong>Pré-requisito ausente:</strong> {postImages.detalhe}{' '}
            <button
              className="tiny"
              onClick={() => api.corrigirPostImages().then(() => window.location.reload())}
            >
              Corrigir agora
            </button>
          </div>
        )}

        <section>
          <div className="section-head">
            <h2>As duas metades do circuito</h2>
            <span className="hint">o MongoDB é a fonte da verdade; o Iceberg é derivado</span>
          </div>
          <div className="grid two">
            <article className="card side">
              <h3>MongoDB Atlas</h3>
              <p className="subtitle">cluster operacional · serve o checkout</p>
              <div className="metric">{fmtInt(mongo?.total)}</div>
              <div className="metric-label">pedidos</div>
              <div style={{ marginTop: 16 }}>
                <div className="kv"><span>Receita</span><span>{fmtBRL(mongo?.receita)}</span></div>
                <div className="kv"><span>Dead-letter queue</span><span>{fmtInt(mongo?.dlq)}</span></div>
                {mongo?.por_status?.slice(0, 3).map((s) => (
                  <div className="kv" key={s.status}><span>{s.status}</span><span>{fmtInt(s.pedidos)}</span></div>
                ))}
              </div>
            </article>

            <article className="card side lake">
              <h3>Apache Iceberg no S3</h3>
              <p className="subtitle">tabela derivada · lida por Athena e Glue</p>
              {iceberg?.disponivel ? (
                <>
                  <div className="metric">{fmtInt(iceberg.total)}</div>
                  <div className="metric-label">linhas · {fmtInt(iceberg.distintos)} ids distintos</div>
                  <div style={{ marginTop: 16 }}>
                    <div className="kv"><span>Tempo da consulta</span><span>{iceberg.tempo_ms} ms</span></div>
                    <div className="kv"><span>Dados escaneados</span><span>{fmtBytes(iceberg.bytes_escaneados)}</span></div>
                    <div className="kv"><span>Colunas no catálogo</span><span>{fmtInt(schema?.colunas?.length)}</span></div>
                  </div>
                </>
              ) : (
                <AvisoAws erro={iceberg?.erro || aws?.detalhe} />
              )}
            </article>
          </div>

          {visao && (
            <div className={`notice ${visao.convergiu ? 'ok' : 'warn'}`}>
              {visao.convergiu ? (
                <>
                  <strong>Convergido.</strong> Os dois lados têm {fmtInt(mongo.total)} pedidos,
                  sem duplicata. Nenhum job de sincronização produziu esse número.
                </>
              ) : duplicada ? (
                <>
                  <strong>Tabela duplicada.</strong> O Iceberg tem {fmtInt(iceberg.total)} linhas
                  para {fmtInt(iceberg.distintos)} ids distintos. Total maior que ids significa que
                  um restart sem checkpoint reexecutou o initialSync — ver docs/TROUBLESHOOTING.md.
                </>
              ) : propagando ? (
                <>
                  <strong>Propagando.</strong> MongoDB tem {fmtInt(mongo?.total)} e o Iceberg
                  tem {fmtInt(iceberg?.total)}, sem duplicata ({fmtInt(iceberg?.distintos)} ids
                  distintos). É o CDC a caminho: leva de 10 a 60 segundos. Recarregue em instantes.
                </>
              ) : iceberg?.disponivel ? (
                <>
                  <strong>Divergente.</strong> MongoDB tem {fmtInt(mongo?.total)} e o Iceberg
                  tem {fmtInt(iceberg?.total)} linhas ({fmtInt(iceberg?.distintos)} ids).
                </>
              ) : (
                <><strong>Só metade do circuito está visível.</strong> O lado MongoDB responde; o Iceberg precisa de credencial AWS.</>
              )}
            </div>
          )}
        </section>

        <section>
          <div className="section-head">
            <h2>Ciclo CDC ao vivo</h2>
            <span className="hint">cada operação leva de 10 a 60 segundos para aparecer no lake</span>
          </div>
          <div className="card">
            <CicloCdc aoMudar={carregar} />
          </div>
        </section>

        <section>
          <div className="section-head">
            <h2>Time travel</h2>
            <span className="hint">ninguém configurou versionamento — vem do formato</span>
          </div>
          <div className="card">
            <TimeTravel />
          </div>
        </section>

        <section>
          <div className="section-head">
            <h2>Consultas analíticas</h2>
            <span className="hint">o relatório que ninguém rodaria no cluster transacional</span>
          </div>
          <div className="card">
            <Consultas />
          </div>
        </section>

        {schema?.colunas?.length > 0 && (
          <section>
            <div className="section-head">
              <h2>Schema no catálogo Glue</h2>
              <span className="hint">campo novo no MongoDB vira coluna aqui, sem migração</span>
            </div>
            <div className="card">
              <div className="grid four">
                {schema.colunas.map((c) => (
                  <div key={c.nome} className="kv">
                    <span className="mono">{c.nome}</span>
                    <span>{c.tipo}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        <footer>
          MongoDB Atlas Stream Processing → Apache Iceberg → S3 + Glue → Athena ·
          {' '}região sa-east-1 · o Iceberg é derivado e descartável: dropar a tabela e
          reiniciar o processor reconstrói tudo a partir do Atlas.
        </footer>
      </main>
    </div>
  )
}
