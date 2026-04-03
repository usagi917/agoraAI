import { describe, expect, it, vi } from 'vitest'
import { isWebGLSupported } from '../useWebGLDetect'

describe('isWebGLSupported', () => {
  it('returns true when WebGL context is available', () => {
    const mockCanvas = {
      getContext: vi.fn().mockReturnValue({}),
    }
    vi.spyOn(document, 'createElement').mockReturnValue(mockCanvas as any)

    expect(isWebGLSupported()).toBe(true)
    expect(mockCanvas.getContext).toHaveBeenCalledWith('webgl')
  })

  it('returns false when WebGL context is null', () => {
    const mockCanvas = {
      getContext: vi.fn().mockReturnValue(null),
    }
    vi.spyOn(document, 'createElement').mockReturnValue(mockCanvas as any)

    expect(isWebGLSupported()).toBe(false)
  })

  it('returns false when createElement throws', () => {
    vi.spyOn(document, 'createElement').mockImplementation(() => {
      throw new Error('no canvas')
    })

    expect(isWebGLSupported()).toBe(false)
  })
})
