import test from 'node:test'
import assert from 'node:assert/strict'
import { avisoDeModo } from '../src/modo.js'

test('modo somente MongoDB vira faixa de alerta com o resumo do backend', () => {
  const a = avisoDeModo({ ok: true, modo: 'somente_mongodb', resumo: 'Modo somente MongoDB: nada é confirmado no lake.' })
  assert.equal(a.classe, 'warn')
  assert.equal(a.titulo, 'Modo somente MongoDB.')
  assert.equal(a.texto, 'nada é confirmado no lake.')
})

test('falha no lado MongoDB vira faixa vermelha', () => {
  assert.equal(avisoDeModo({ ok: false, modo: 'com_falha', resumo: 'x' }).classe, 'bad')
})

test('demo completa, resposta antiga ou ausente não mostra faixa', () => {
  assert.equal(avisoDeModo({ modo: 'completo', resumo: 'ok' }), null)
  assert.equal(avisoDeModo({ ok: true, checks: [] }), null)
  assert.equal(avisoDeModo(null), null)
})
