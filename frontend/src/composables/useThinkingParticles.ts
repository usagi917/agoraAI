import * as THREE from 'three'

const DISSOLVE_DURATION = 600

export type ThinkingVisualMode = 'idle' | 'graphrag' | 'simulation' | 'swarm' | 'report' | 'society'

const MODE_PRESETS: Record<ThinkingVisualMode, { color: number; secondaryColor: number; particleCount: number; orbitRadius: number; size: number; opacity: number; speedBase: number }> = {
  idle: {
    color: 0x6aa7ff,
    secondaryColor: 0x91f2ff,
    particleCount: 54,
    orbitRadius: 72,
    size: 2.6,
    opacity: 0.46,
    speedBase: 0.002,
  },
  graphrag: {
    color: 0x52f1c9,
    secondaryColor: 0x8effd0,
    particleCount: 76,
    orbitRadius: 94,
    size: 3.1,
    opacity: 0.62,
    speedBase: 0.0033,
  },
  simulation: {
    color: 0xffb067,
    secondaryColor: 0xffdf92,
    particleCount: 64,
    orbitRadius: 84,
    size: 2.9,
    opacity: 0.56,
    speedBase: 0.0026,
  },
  swarm: {
    color: 0x8d7dff,
    secondaryColor: 0xd4c4ff,
    particleCount: 88,
    orbitRadius: 108,
    size: 2.8,
    opacity: 0.58,
    speedBase: 0.003,
  },
  report: {
    color: 0xff8f70,
    secondaryColor: 0xffd39a,
    particleCount: 48,
    orbitRadius: 66,
    size: 3.3,
    opacity: 0.52,
    speedBase: 0.0018,
  },
  society: {
    color: 0x66bb6a,
    secondaryColor: 0xb39ddb,
    particleCount: 72,
    orbitRadius: 96,
    size: 2.6,
    opacity: 0.54,
    speedBase: 0.0024,
  },
}

export function startThinkingAnimation(
  scene: THREE.Scene,
  options: { mode?: ThinkingVisualMode } = {},
): () => void {
  const preset = MODE_PRESETS[options.mode ?? 'idle']
  const particleCount = preset.particleCount
  const positions = new Float32Array(particleCount * 3)
  const velocities: { theta: number; phi: number; r: number; speed: number }[] = []

  for (let i = 0; i < particleCount; i++) {
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    const r = preset.orbitRadius * (0.38 + Math.random() * 0.68)
    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta)
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
    positions[i * 3 + 2] = r * Math.cos(phi)
    velocities.push({
      theta,
      phi,
      r,
      speed: preset.speedBase + Math.random() * preset.speedBase * 1.4,
    })
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))

  const material = new THREE.PointsMaterial({
    color: preset.color,
    size: preset.size,
    transparent: true,
    opacity: preset.opacity,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: true,
  })

  const points = new THREE.Points(geometry, material)
  points.name = '__thinking_particles'
  scene.add(points)

  const ringGeometry = new THREE.RingGeometry(preset.orbitRadius * 0.9, preset.orbitRadius * 0.94, 96)
  const ringMaterial = new THREE.MeshBasicMaterial({
    color: preset.secondaryColor,
    transparent: true,
    opacity: 0.1,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  })
  const ring = new THREE.Mesh(ringGeometry, ringMaterial)
  ring.name = '__thinking_ring'
  ring.rotation.x = Math.PI / 2.4
  scene.add(ring)

  let animId: number | null = null
  let dissolving = false
  let dissolveStart = 0

  function animate() {
    const posAttr = geometry.getAttribute('position') as THREE.BufferAttribute

    if (dissolving) {
      const elapsed = performance.now() - dissolveStart
      const t = Math.min(elapsed / DISSOLVE_DURATION, 1)
      material.opacity = preset.opacity * (1 - t)
      material.size = preset.size * (1 - t * 0.5)
      ringMaterial.opacity = 0.1 * (1 - t)

      if (t >= 1) {
        cleanup()
        return
      }
    }

    for (let i = 0; i < particleCount; i++) {
      const v = velocities[i]
      v.theta += v.speed
      v.phi += v.speed * 0.3
      posAttr.setXYZ(
        i,
        v.r * Math.sin(v.phi) * Math.cos(v.theta),
        v.r * Math.sin(v.phi) * Math.sin(v.theta),
        v.r * Math.cos(v.phi),
      )
    }
    posAttr.needsUpdate = true
    points.rotation.y += preset.speedBase * 0.7
    ring.rotation.z += preset.speedBase * 0.9

    animId = requestAnimationFrame(animate)
  }

  animId = requestAnimationFrame(animate)

  function cleanup() {
    if (animId != null) {
      cancelAnimationFrame(animId)
      animId = null
    }
    scene.remove(points)
    scene.remove(ring)
    geometry.dispose()
    material.dispose()
    ringGeometry.dispose()
    ringMaterial.dispose()
  }

  function stop() {
    if (dissolving) return
    dissolving = true
    dissolveStart = performance.now()
  }

  return stop
}
