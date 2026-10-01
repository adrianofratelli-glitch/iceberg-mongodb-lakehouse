export default function AvisoAws({ erro }) {
  if (!erro) return null
  const expirada = /expirad|ausente|NoCredentials/i.test(erro)
  return (
    <div className={`notice ${expirada ? 'warn' : 'bad'}`}>
      <strong>{expirada ? 'Credencial AWS indisponível.' : 'A consulta ao Athena falhou.'}</strong>{' '}
      {erro}
      {expirada && (
        <>
          {' '}Cole um bloco novo do portal SSO em <code>~/.aws/credentials</code> A PoV se recupera sozinha em alguns segundos.
          O lado MongoDB continua funcionando.
        </>
      )}
    </div>
  )
}
