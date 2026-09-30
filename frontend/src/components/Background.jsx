import { useEffect, useRef } from 'react'

/**
 * Always-running, GPU-friendly background: drifting record nodes, relationship lines, data packets
 * travelling along connections, pulsing hubs, a slowly scrolling timeline track, plus CSS gradient
 * blobs and a panning grid. Adapts colours to the theme; slows down (never stops) for reduced motion.
 */
export default function Background({ density = 1 }) {
  const ref = useRef(null)

  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas.getContext('2d', { alpha: true })
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    let speed = reduce?.matches ? 0.28 : 1
    let W = 0, H = 0, dpr = 1, raf = 0, last = performance.now()
    let nodes = [], packets = [], ticks = [], lastSpawn = 0
    const mouse = { x: -9999, y: -9999 }
    let colors = readColors()

    function readColors() {
      const cs = getComputedStyle(document.documentElement)
      return {
        a: cs.getPropertyValue('--bg-canvas-node').trim() || '232,168,107',
        b: cs.getPropertyValue('--bg-canvas-node2').trim() || '232,195,158',
        l: cs.getPropertyValue('--bg-canvas-line').trim() || '214,170,130',
        light: document.documentElement.getAttribute('data-theme') === 'light',
      }
    }

    function init() {
      dpr = Math.min(window.devicePixelRatio || 1, 1.5)
      W = window.innerWidth; H = window.innerHeight
      canvas.width = W * dpr; canvas.height = H * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const count = Math.round(Math.min(86, Math.max(26, (W * H) / 17000)) * density)
      nodes = Array.from({ length: count }, (_, i) => {
        const kind = i % 11 === 0 ? 'doc' : i % 7 === 0 ? 'hub' : 'dot'
        return {
          x: Math.random() * W, y: Math.random() * H,
          vx: (Math.random() - 0.5) * 0.22, vy: (Math.random() - 0.5) * 0.22,
          r: kind === 'hub' ? 2.6 : kind === 'doc' ? 0 : 1.2 + Math.random() * 1.3,
          kind, c: Math.random() > 0.55 ? 'b' : 'a', phase: Math.random() * Math.PI * 2,
          rot: (Math.random() - 0.5) * 0.4,
        }
      })
      ticks = Array.from({ length: Math.ceil(W / 90) + 2 }, (_, i) => ({ x: i * 90, ev: Math.random() > 0.72 }))
      packets = []
    }

    const LINK = 150
    function frame(now) {
      raf = requestAnimationFrame(frame)
      if (document.hidden) { last = now; return }
      const dt = Math.min(50, now - last) / 16.67 * speed
      last = now
      ctx.clearRect(0, 0, W, H)
      const { a, b, l, light } = colors
      const lineA = light ? 0.20 : 0.26

      // move nodes
      for (const n of nodes) {
        n.x += n.vx * dt; n.y += n.vy * dt; n.phase += 0.02 * dt
        if (n.x < -30) n.x = W + 30; if (n.x > W + 30) n.x = -30
        if (n.y < -30) n.y = H + 30; if (n.y > H + 30) n.y = -30
      }
      // links
      const links = []
      ctx.lineWidth = 1
      for (let i = 0; i < nodes.length; i++) {
        const p = nodes[i]
        for (let j = i + 1; j < nodes.length; j++) {
          const q = nodes[j]
          const dx = p.x - q.x, dy = p.y - q.y
          const d2 = dx * dx + dy * dy
          if (d2 < LINK * LINK) {
            const d = Math.sqrt(d2)
            const md = Math.hypot((p.x + q.x) / 2 - mouse.x, (p.y + q.y) / 2 - mouse.y)
            const boost = md < 180 ? (1 - md / 180) * 0.35 : 0
            ctx.strokeStyle = `rgba(${l},${(1 - d / LINK) * lineA + boost})`
            ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke()
            links.push([i, j])
          }
        }
      }
      // data packets travelling along relationships
      if (now - lastSpawn > (reduce?.matches ? 1400 : 320) && links.length && packets.length < 22) {
        const [i, j] = links[(Math.random() * links.length) | 0]
        packets.push(Math.random() > 0.5 ? { i, j, t: 0, s: 0.008 + Math.random() * 0.01 } : { i: j, j: i, t: 0, s: 0.008 + Math.random() * 0.01 })
        lastSpawn = now
      }
      for (let k = packets.length - 1; k >= 0; k--) {
        const pk = packets[k]
        pk.t += pk.s * dt
        const p = nodes[pk.i], q = nodes[pk.j]
        if (pk.t >= 1 || !p || !q || Math.hypot(p.x - q.x, p.y - q.y) > LINK * 1.15) { packets.splice(k, 1); continue }
        const x = p.x + (q.x - p.x) * pk.t, y = p.y + (q.y - p.y) * pk.t
        const g = ctx.createRadialGradient(x, y, 0, x, y, 7)
        g.addColorStop(0, `rgba(${b},${light ? 0.55 : 0.9})`); g.addColorStop(1, `rgba(${b},0)`)
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 7, 0, Math.PI * 2); ctx.fill()
      }
      // nodes
      for (const n of nodes) {
        const col = n.c === 'a' ? a : b
        if (n.kind === 'doc') {
          ctx.save(); ctx.translate(n.x, n.y); ctx.rotate(n.rot)
          ctx.strokeStyle = `rgba(${col},${light ? 0.35 : 0.45})`; ctx.lineWidth = 1.2
          ctx.beginPath(); ctx.moveTo(-6, -8); ctx.lineTo(3, -8); ctx.lineTo(6, -5); ctx.lineTo(6, 8); ctx.lineTo(-6, 8); ctx.closePath(); ctx.stroke()
          ctx.beginPath(); ctx.moveTo(-3, -2); ctx.lineTo(3, -2); ctx.moveTo(-3, 2); ctx.lineTo(3, 2); ctx.stroke()
          ctx.restore()
          continue
        }
        const pulse = n.kind === 'hub' ? (Math.sin(n.phase) + 1) / 2 : 0
        if (n.kind === 'hub') {
          ctx.strokeStyle = `rgba(${col},${0.35 * (1 - pulse)})`
          ctx.beginPath(); ctx.arc(n.x, n.y, 4 + pulse * 12, 0, Math.PI * 2); ctx.stroke()
          const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, 14)
          g.addColorStop(0, `rgba(${col},${light ? 0.35 : 0.5})`); g.addColorStop(1, `rgba(${col},0)`)
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(n.x, n.y, 14, 0, Math.PI * 2); ctx.fill()
        }
        ctx.fillStyle = `rgba(${col},${light ? 0.55 : 0.8})`
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx.fill()
      }
      // chronology track (scrolling timeline)
      const ty = H - 46
      ctx.strokeStyle = `rgba(${l},${light ? 0.12 : 0.14})`; ctx.lineWidth = 1
      ctx.beginPath(); ctx.moveTo(0, ty); ctx.lineTo(W, ty); ctx.stroke()
      for (const t of ticks) {
        t.x -= 0.25 * dt
        if (t.x < -20) { t.x += ticks.length * 90; t.ev = Math.random() > 0.72 }
        ctx.beginPath(); ctx.moveTo(t.x, ty - 4); ctx.lineTo(t.x, ty + 4); ctx.stroke()
        if (t.ev) {
          ctx.fillStyle = `rgba(${b},${light ? 0.35 : 0.45})`
          ctx.beginPath(); ctx.arc(t.x + 45, ty, 2.6, 0, Math.PI * 2); ctx.fill()
        }
      }
    }

    const onResize = () => init()
    const onMove = (e) => { mouse.x = e.clientX; mouse.y = e.clientY }
    const onLeave = () => { mouse.x = mouse.y = -9999 }
    const onMotion = () => { speed = reduce.matches ? 0.28 : 1 }
    const mo = new MutationObserver(() => { colors = readColors() })
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    init()
    raf = requestAnimationFrame(frame)
    window.addEventListener('resize', onResize)
    window.addEventListener('pointermove', onMove, { passive: true })
    document.addEventListener('pointerleave', onLeave)
    reduce?.addEventListener?.('change', onMotion)
    return () => {
      cancelAnimationFrame(raf); mo.disconnect()
      window.removeEventListener('resize', onResize)
      window.removeEventListener('pointermove', onMove)
      document.removeEventListener('pointerleave', onLeave)
      reduce?.removeEventListener?.('change', onMotion)
    }
  }, [density])

  return (
    <div className="bg-layer" aria-hidden>
      <div className="bg-blob b1" /><div className="bg-blob b2" /><div className="bg-blob b3" />
      <div className="bg-grid" />
      <canvas ref={ref} />
      <div className="bg-vignette" />
    </div>
  )
}
