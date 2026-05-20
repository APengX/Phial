<template>
  <div ref="wrap" class="graph-wrap">
    <canvas
      ref="cv"
      class="graph-cv"
      @mousedown="onDown"
      @mousemove="onMove"
      @mouseup="onUp"
      @mouseleave="onUp"
      @wheel.prevent="onWheel"
    ></canvas>
    <div v-if="error" class="graph-msg muted">{{ error }}</div>
    <div v-else-if="ready && !count" class="graph-msg muted">{{ t('nav.graphEmpty') }}</div>
    <div v-if="legend && count" class="graph-legend">
      <span><i class="ln link"></i>{{ t('nav.edgeLink') }}</span>
      <span><i class="ln ctx"></i>{{ t('nav.edgeContext') }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getGraph } from '@/api/graph'

const props = defineProps({
  activePath: { type: String, default: '' },
  legend: { type: Boolean, default: true }
})
const emit = defineEmits(['open'])
const { t } = useI18n()

const wrap = ref(null)
const cv = ref(null)
const error = ref('')
const ready = ref(false)
const count = ref(0)

let g2d = null
let dpr = 1
let cssW = 300
let cssH = 300
let centered = false

// world -> screen:  screen = world * scale + offset
let scale = 1
let offX = 150
let offY = 150

let N = []   // nodes  {path,title,degree,x,y,vx,vy}
let E = []   // edges  {s,t,kind}  (s/t are node refs)

// force-sim constants
const REPULSE = 2200
const LINK_LEN = 66
const SPRING = 0.05
const CENTER = 0.02
const DAMP = 0.84

let alpha = 0
let raf = 0

// interaction state
let dragNode = null
let panning = false
let last = { x: 0, y: 0 }
let downAt = { x: 0, y: 0 }
let moved = false
let hoverNode = null
let ro = null

function nodeRadius(n) {
  return 4 + Math.min(10, Math.sqrt(n.degree || 0) * 2.4)
}
function rel(e) {
  const r = cv.value.getBoundingClientRect()
  return { x: e.clientX - r.left, y: e.clientY - r.top }
}
function toWorld(mx, my) {
  return { x: (mx - offX) / scale, y: (my - offY) / scale }
}
function hitTest(mx, my) {
  const w = toWorld(mx, my)
  for (let i = N.length - 1; i >= 0; i--) {
    const n = N[i]
    const r = nodeRadius(n) + 4
    const rw = r / scale
    if ((n.x - w.x) ** 2 + (n.y - w.y) ** 2 <= rw * rw) return n
  }
  return null
}

async function load() {
  try {
    const data = await getGraph()
    const gn = data.nodes || []
    const spread = Math.max(70, Math.min(cssW, cssH) / 2.2)
    N = gn.map((d, i) => {
      const a = (i / Math.max(1, gn.length)) * Math.PI * 2
      const rr = spread * (0.55 + Math.random() * 0.5)
      return { ...d, x: Math.cos(a) * rr, y: Math.sin(a) * rr, vx: 0, vy: 0 }
    })
    const byPath = {}
    N.forEach((n) => { byPath[n.path] = n })
    E = (data.edges || [])
      .map((e) => ({ s: byPath[e.source], t: byPath[e.target], kind: e.kind }))
      .filter((e) => e.s && e.t)
    count.value = N.length
    ready.value = true
    alpha = 1
    kick()
  } catch (e) {
    error.value = e.message || 'failed to load graph'
    ready.value = true
  }
}

function step() {
  if (alpha < 0.005 && !dragNode) return false
  const a = Math.max(alpha, dragNode ? 0.3 : 0)
  const n = N.length
  // repulsion (every pair) — fine for a typical workspace
  for (let i = 0; i < n; i++) {
    const p = N[i]
    for (let j = i + 1; j < n; j++) {
      const q = N[j]
      let dx = p.x - q.x
      let dy = p.y - q.y
      let d2 = dx * dx + dy * dy
      if (d2 < 0.01) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; d2 = 0.01 }
      const d = Math.sqrt(d2)
      const f = (REPULSE / d2) * a
      const fx = (dx / d) * f
      const fy = (dy / d) * f
      p.vx += fx; p.vy += fy
      q.vx -= fx; q.vy -= fy
    }
  }
  // springs along edges
  for (const e of E) {
    let dx = e.t.x - e.s.x
    let dy = e.t.y - e.s.y
    const d = Math.sqrt(dx * dx + dy * dy) || 0.01
    const f = (d - LINK_LEN) * SPRING * a
    const fx = (dx / d) * f
    const fy = (dy / d) * f
    e.s.vx += fx; e.s.vy += fy
    e.t.vx -= fx; e.t.vy -= fy
  }
  // gravity toward origin + integrate
  for (const p of N) {
    p.vx -= p.x * CENTER * a
    p.vy -= p.y * CENTER * a
    if (p === dragNode) { p.vx = 0; p.vy = 0; continue }
    p.vx *= DAMP
    p.vy *= DAMP
    p.x += p.vx
    p.y += p.vy
  }
  alpha *= 0.985
  return alpha > 0.005
}

function draw() {
  if (!g2d) return
  g2d.setTransform(dpr, 0, 0, dpr, 0, 0)
  g2d.clearRect(0, 0, cssW, cssH)
  g2d.translate(offX, offY)
  g2d.scale(scale, scale)

  for (const e of E) {
    g2d.beginPath()
    g2d.moveTo(e.s.x, e.s.y)
    g2d.lineTo(e.t.x, e.t.y)
    if (e.kind === 'context') {
      g2d.strokeStyle = 'rgba(217,119,87,0.45)'
      g2d.setLineDash([3, 3])
    } else {
      g2d.strokeStyle = 'rgba(111,110,103,0.34)'
      g2d.setLineDash([])
    }
    g2d.lineWidth = 1 / scale
    g2d.stroke()
  }
  g2d.setLineDash([])

  for (const n of N) {
    const r = nodeRadius(n)
    const active = n.path === props.activePath
    const hov = n === hoverNode
    g2d.beginPath()
    g2d.arc(n.x, n.y, r, 0, Math.PI * 2)
    g2d.fillStyle = active ? '#d97757' : n.degree ? '#e3a98f' : '#cdcabf'
    g2d.fill()
    if (active || hov) {
      g2d.lineWidth = 2 / scale
      g2d.strokeStyle = '#b85c3e'
      g2d.stroke()
    }
    if (scale > 0.5 || active || hov) {
      const label = n.title || n.path
      const short = label.length > 24 ? label.slice(0, 23) + '…' : label
      g2d.fillStyle = active ? '#b85c3e' : '#57564f'
      g2d.font = `${hov || active ? 600 : 400} ${11 / scale}px -apple-system, "PingFang SC", sans-serif`
      g2d.textAlign = 'center'
      g2d.fillText(short, n.x, n.y + r + 12 / scale)
    }
  }
}

function loop() {
  raf = 0
  const moving = step()
  draw()
  if (moving || dragNode) raf = requestAnimationFrame(loop)
}
function kick() {
  if (!raf) raf = requestAnimationFrame(loop)
}

function resize() {
  if (!wrap.value || !cv.value) return
  const r = wrap.value.getBoundingClientRect()
  cssW = Math.max(1, r.width)
  cssH = Math.max(1, r.height)
  dpr = window.devicePixelRatio || 1
  cv.value.width = Math.round(cssW * dpr)
  cv.value.height = Math.round(cssH * dpr)
  cv.value.style.width = cssW + 'px'
  cv.value.style.height = cssH + 'px'
  if (!centered) {
    offX = cssW / 2
    offY = cssH / 2
    centered = true
  }
  kick()
}

// --- pointer interaction -----------------------------------------------------
function onDown(e) {
  const p = rel(e)
  downAt = p
  last = p
  moved = false
  const n = hitTest(p.x, p.y)
  if (n) {
    dragNode = n
    alpha = Math.max(alpha, 0.3)
  } else {
    panning = true
  }
  kick()
}
function onMove(e) {
  const p = rel(e)
  if (dragNode) {
    const w = toWorld(p.x, p.y)
    dragNode.x = w.x
    dragNode.y = w.y
    dragNode.vx = 0
    dragNode.vy = 0
    alpha = Math.max(alpha, 0.3)
    if (Math.abs(p.x - downAt.x) + Math.abs(p.y - downAt.y) > 4) moved = true
    kick()
  } else if (panning) {
    offX += p.x - last.x
    offY += p.y - last.y
    last = p
    moved = true
    kick()
  } else {
    const n = hitTest(p.x, p.y)
    if (n !== hoverNode) {
      hoverNode = n
      if (cv.value) cv.value.style.cursor = n ? 'pointer' : 'grab'
      kick()
    }
  }
}
function onUp() {
  if (dragNode && !moved) emit('open', dragNode.path)
  dragNode = null
  panning = false
}
function onWheel(e) {
  const p = rel(e)
  const next = Math.max(0.25, Math.min(3, scale * (e.deltaY < 0 ? 1.12 : 1 / 1.12)))
  const wx = (p.x - offX) / scale
  const wy = (p.y - offY) / scale
  scale = next
  offX = p.x - wx * scale
  offY = p.y - wy * scale
  kick()
}

watch(() => props.activePath, kick)

onMounted(() => {
  g2d = cv.value.getContext('2d')
  resize()
  ro = new ResizeObserver(resize)
  ro.observe(wrap.value)
  load()
})
onBeforeUnmount(() => {
  if (raf) cancelAnimationFrame(raf)
  if (ro) ro.disconnect()
})
</script>

<style scoped>
.graph-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background:
    radial-gradient(circle at 1px 1px, rgba(0, 0, 0, 0.05) 1px, transparent 0)
    0 0 / 22px 22px,
    var(--bg);
}
.graph-cv { display: block; cursor: grab; }
.graph-cv:active { cursor: grabbing; }
.graph-msg {
  position: absolute; inset: 0; display: flex;
  align-items: center; justify-content: center;
  padding: 24px; text-align: center; font-size: 12.5px; line-height: 1.6;
}
.graph-legend {
  position: absolute; left: 10px; bottom: 10px;
  display: flex; flex-direction: column; gap: 4px;
  font-size: 11px; color: var(--text-dim);
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 6px; padding: 6px 9px;
}
.graph-legend span { display: flex; align-items: center; gap: 6px; }
.graph-legend .ln { width: 16px; height: 0; display: inline-block; }
.graph-legend .ln.link { border-top: 2px solid rgba(120, 120, 120, 0.7); }
.graph-legend .ln.ctx { border-top: 2px dashed var(--accent); }
</style>
