import { vi } from 'vitest'

Object.defineProperty(window, 'alert', {
  writable: true,
  value: vi.fn(),
})
