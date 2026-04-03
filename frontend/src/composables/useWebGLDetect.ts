export function isWebGLSupported(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return canvas.getContext('webgl') !== null
  } catch {
    return false
  }
}
