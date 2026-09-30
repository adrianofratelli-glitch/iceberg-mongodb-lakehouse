# Telas e fluxos da interface

Frontend React (Vite) em `frontend/src/`, servido em `:5250`, consumindo o
backend FastAPI em `:8250` (`frontend/src/api.js`). Tela única (`App.jsx`)
com seções sequenciais, sem roteamento — pensada para apresentação ao vivo,
de cima para baixo.

## Estrutura de componentes

```
App.jsx
 ├─ topbar: marca, pill de estado geral, pill de lag do checkpoint
 ├─ hero: título da demo
 ├─ seção "duas metades do circuito"
 │   ├─ card MongoDB Atlas
 │   ├─ card Apache Iceberg no S3 → AvisoAws.jsx (se faltar credencial)
 │   └─ notice de convergência
 ├─ seção "ciclo CDC ao vivo" → CicloCdc.jsx → QueryDetails.jsx
 ├─ <details> "time travel" → TimeTravel.jsx → Tabela.jsx, AvisoAws.jsx
 └─ <details> "consultas analíticas" → Consultas.jsx → Tabela.jsx, QueryDetails.jsx
```

Componentes de apoio reutilizados em várias seções:
- `AvisoAws.jsx` — banner de erro/aviso quando o Athena está indisponível.
  Diferencia "credencial expirada/ausente" (aviso amarelo, explica que o
  MongoDB continua funcionando) de "consulta falhou por outro motivo" (aviso
  vermelho).
- `Tabela.jsx` — tabela genérica de colunas/linhas retornadas pelo Athena,
  com suporte a linha selecionável (usado no time travel).
- `QueryDetails.jsx` — painel expansível com a query/pipeline real que acabou
  de rodar (Mongo ou Athena) e o `explain`, para o engenheiro mostrar ao vivo
  "foi isso que rodou".

## Fluxo 1 — Carregamento inicial (`App.jsx`)

Ao montar, dispara em paralelo:
- `GET /api/visao-geral` → estado dos dois lados (Mongo/Iceberg).
- `GET /api/schema` → contagem de colunas no catálogo Glue.
- `GET /preflight` → checagens de saúde (conexão, post-images, DLQ, credencial AWS).
- `GET /api/lag` → distância do checkpoint do processor até a janela do oplog.

A pill de estado no topo (`estado`, linhas 39-49 de `App.jsx`) classifica em:
`carregando` → `convergido` (ok) → `tabela duplicada` (bad, `total > ids`
no Iceberg) → `propagando` (warn, contagens diferentes mas sem duplicata) →
`divergente` (warn) → `iceberg offline` (warn). A distinção entre "duplicada"
e "propagando" existe para não soar alarme falso quando o CDC só está a
caminho (10-60s de latência esperada).

Se `changeStreamPreAndPostImages` estiver desabilitado, aparece um aviso com
botão "Corrigir agora", que chama `POST /api/corrigir/post-images`.

Screenshot: `docs/screenshots/01-duas-metades.png` — os dois cards lado a
lado, MongoDB com 5.000 pedidos e Iceberg com 5.000 linhas, estado
convergido.

## Fluxo 2 — Ciclo CDC ao vivo (`CicloCdc.jsx`)

Quatro botões de operação — INSERT, UPDATE, DELETE, CAMPO NOVO — mais um
botão "Limpar" (reset). Cada clique:

1. Chama `POST /api/demo/{insert|update|delete|schema}`.
2. Mostra o documento MongoDB resultante e os detalhes da query/operação
   (`QueryDetails`).
3. Entra em polling (`esperarPropagacao`, a cada 3s, até 40 tentativas = 2min)
   chamando `GET /api/pedido/{id}` até o lado Iceberg refletir a mudança
   esperada (linha existir/sumir, status bater no caso de update).
4. Mostra uma timeline com dois passos — "MONGODB" (concluído) e "ICEBERG"
   (aguardando… Xs / refletido em Xs).
5. Renderiza a linha da tabela Iceberg retornada, ou "0 linhas — o delete
   propagou" quando aplicável.

Se o Iceberg responder erro (ex.: credencial AWS), mostra `AvisoAws` em vez
da tabela.

Screenshots:
- `docs/screenshots/02-ciclo-cdc.png` — INSERT: pedido em MongoDB e a mesma
  linha refletida no Iceberg após alguns segundos, com o tempo decorrido
  visível.
- `docs/screenshots/03-update-refletido.png` — UPDATE: status
  `EM_TRANSPORTE` e novo valor já refletidos na tabela Iceberg.

## Fluxo 3 — Time travel (`TimeTravel.jsx`, dentro de `<details>` colapsável)

1. Ao abrir, chama `GET /api/snapshots` → lista de snapshots Iceberg
   (snapshot_id, `committed_at`, operação, registros adicionados/removidos).
2. Clicar numa linha da tabela chama `GET
   /api/snapshots/{snapshot_id}/pedido/PED-AOVIVO-001` e mostra se o pedido
   existia naquele snapshot e com quais valores, ou explica que é anterior ao
   insert / posterior ao delete.

Screenshot: `docs/screenshots/04-time-travel.png` — histórico de snapshots
com operações `append`, `overwrite` e `delete`.

## Fluxo 4 — Consultas analíticas (`Consultas.jsx`, também em `<details>`)

1. `GET /api/consultas` lista os arquivos de `sql/` (id, nome do arquivo,
   título extraído do primeiro comentário `--`).
2. Clicar num botão roda `POST /api/consultas/{id}`, que executa a query no
   Athena e devolve colunas/linhas, tempo de execução e bytes escaneados.
3. Resultado renderizado em `Tabela`, com nota explícita de "sem nenhum
   impacto no cluster operacional" e painel `QueryDetails` com o SQL e as
   métricas.

Screenshot: `docs/screenshots/05-consulta-analitica.png` — resultado da
consulta de receita por UF/mês com tempo de scan e bytes escaneados visíveis.

## Sinal de lag do checkpoint (topbar)

Pill adicional ao lado do estado geral, alimentada por `GET /api/lag`
(`backend/lag_side.py`). Estados: `OK`, `ALERTA`, `CRÍTICO — restart próximo
pode duplicar dados`, ou oculto se a checagem não está configurada
(`STREAM_PROCESSING_URI` ausente) ou sem acesso ao oplog. Serve para avisar
antes do processor falhar de vez com "resume of change stream was not
possible" — nesse ponto a recuperação sem duplicar a tabela já não é mais
possível.

## Onde estão os arquivos

| Componente | Arquivo |
|---|---|
| Shell/orquestração | `frontend/src/App.jsx` |
| Cliente HTTP | `frontend/src/api.js` |
| Ciclo CDC (insert/update/delete/schema) | `frontend/src/components/CicloCdc.jsx` |
| Time travel | `frontend/src/components/TimeTravel.jsx` |
| Consultas analíticas | `frontend/src/components/Consultas.jsx` |
| Tabela genérica de resultados | `frontend/src/components/Tabela.jsx` |
| Painel de query/explain | `frontend/src/components/QueryDetails.jsx` |
| Aviso de credencial/erro AWS | `frontend/src/components/AvisoAws.jsx` |
| Estilos de marca (não editar sem checar sincronismo) | `frontend/src/pov-signature.css` |
| Estilos gerais | `frontend/src/index.css` |

Antes de mexer no frontend, ler `POV_UI_DESIGN_SYSTEM.md` na raiz do
workspace (fora deste repo) e validar em 1440px, 768px e 360px, sem erro de
console e sem overflow horizontal.
