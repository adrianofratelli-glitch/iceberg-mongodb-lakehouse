# ADR 0003 — Direito ao esquecimento no lake fica fora da `main`

- Status: aceita (2026-10-15, registrada em 2026-11-12)

## Contexto
Um DELETE no MongoDB remove a linha da versão atual da tabela Iceberg, mas os
snapshots anteriores continuam guardando os arquivos com a linha (o time travel
da demo a mostra de volta). Apagar de verdade exige reescrever os arquivos
(OPTIMIZE), expirar snapshots e remover arquivos órfãos (VACUUM), e conferir
por snapshot que nada sobrou.

Uma implementação disso (rota, script e painel, com expurgo protegido por flag)
foi escrita em 2026-10-09 na branch `review/opus-night`, mas nunca rodou contra
a AWS real: a credencial estava expirada. Também não foi validado como o
processor do ASP convive com OPTIMIZE/VACUUM feitos por outro motor na mesma
tabela.

## Decisão
Não integrar à `main` até rodar ponta a ponta contra a AWS. Enquanto isso, a
documentação e a UI dizem que DELETE não é apagamento.

## Consequências
- README, roteiro e botão DELETE não prometem direito ao esquecimento.
- Para integrar: renovar a credencial, rodar a branch contra um pedido de
  sonda, provar por snapshot que a linha sumiu de todas as versões e que o
  processor segue escrevendo depois do VACUUM.
