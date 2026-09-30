export default function Tabela({ colunas, linhas, selecionada, aoClicar, vazio }) {
  if (!colunas?.length || !linhas?.length) {
    return <p className="empty">{vazio || 'Nenhuma linha retornada.'}</p>
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {colunas.map((c) => (
              <th key={c} scope="col">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {linhas.map((linha, i) => (
            <tr
              key={i}
              className={selecionada === i ? 'selected' : undefined}
              onClick={aoClicar ? () => aoClicar(linha, i) : undefined}
              style={aoClicar ? { cursor: 'pointer' } : undefined}
            >
              {linha.map((celula, j) => (
                <td key={j}>{celula === '' ? '—' : celula}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
