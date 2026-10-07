export default function AvisoAws({ erro }) {
  if (!erro) return null
  const expirada = /expirad|ausente|NoCredentials/i.test(erro)
  // O backend já costuma mandar a instrução; não repetir na mesma frase.
  const jaInstrui = /Cole um bloco novo/i.test(erro)
  return (
    <div className={`notice ${expirada ? 'warn' : 'bad'}`}>
      <strong>{expirada ? 'Credencial AWS indisponível.' : 'A consulta ao Athena falhou.'}</strong>{' '}
      {erro}
      {expirada && (
        <>
          {!jaInstrui && <>{' '}Cole um bloco novo do portal SSO em <code>~/.aws/credentials</code>.</>}
          {' '}A PoV se recupera sozinha em alguns segundos.
          O lado MongoDB continua funcionando.
        </>
      )}
    </div>
  )
}
