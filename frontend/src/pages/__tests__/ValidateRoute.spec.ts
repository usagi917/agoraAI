import { describe, expect, it } from 'vitest'
import router from '../../router'

describe('validate route', () => {
  it('resolves validate routes with and without id', () => {
    expect(router.resolve('/validate').name).toBe('validate')
    expect(router.resolve('/validate/sim-1').name).toBe('validate')
  })
})
