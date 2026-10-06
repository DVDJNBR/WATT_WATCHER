/**
 * PipelineDiagram — a direct port of the validated mockup
 * (app_v2/mockups/pipeline-block.html): one shared scene, auto-cycling
 * through every source. Each lap is a chain of discrete facts, not a
 * progress bar on a shared timeline — the bead travels a connector, that
 * fact ends, the block it reaches lights up (holds, it's a trace of what
 * just passed through) and its preview flashes (peaks, then fades — it
 * shows what the data just became, not where it is), that fact ends, the
 * bead leaves again. A click on a source jumps the chain to it immediately.
 *
 * Bronze/Silver/Gold/Endpoints/Dashboard are grouped under the real Azure
 * services that host them (ADLS Gen2 / SQL Server / Function App / Static
 * Web Apps) — this reflects the certification-era (v1) architecture this
 * portfolio piece is built to explain, not the cost-trimmed v2 deployment
 * actually serving this page today (see `watt_watcher_unazureing` —
 * deliberate, not stale).
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SOURCES, CABLE_NOTES } from '../../data/pipelineSources.js'
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion.js'
import { PreviewPanel } from './PreviewPanel.jsx'

const TRAVEL_MS = 500
const FLASH_PEAK_MS = 250
const STAGE_FLASH_MS = FLASH_PEAK_MS + 450 // block: peak then held
const PEEK_FLASH_MS = FLASH_PEAK_MS + 750  // preview: peak then decays to neutral
const LOOP_PAUSE_MS = 400

const STAGE_KINDS = ['bronze', 'silver', 'gold', 'api', 'dashboard']

function cancelAnim(el) { if (el) el.getAnimations().forEach(a => a.cancel()) }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }

// Contour of a block: the whole perimeter (outline, not just top/bottom)
// lights at once, passes through a wide blurred halo at its peak, then
// STAYS lit — a trace of the pass, held until the next lap resets it.
function lightNode(el, color, glow) {
  if (!el) return Promise.resolve()
  cancelAnim(el)
  const anim = el.animate([
    { offset: 0, outlineColor: 'transparent', boxShadow: `0 0 0 0 ${glow}` },
    { offset: FLASH_PEAK_MS / STAGE_FLASH_MS, outlineColor: color, boxShadow: `0 0 26px 8px ${glow}` },
    { offset: 1, outlineColor: color, boxShadow: `0 0 0 0 ${glow}` },
  ], { duration: STAGE_FLASH_MS, fill: 'forwards', easing: 'linear' })
  return anim.finished.catch(() => {})
}

// Halo of a data preview: lights, peaks, then returns to neutral — a
// preview shows what the data just BECAME at this step, not where it is;
// unlike a block, it must not stay lit.
function flashPeek(el, color, glow) {
  if (!el) return Promise.resolve()
  cancelAnim(el)
  const anim = el.animate([
    { offset: 0, outlineColor: 'transparent', boxShadow: `0 0 0 0 ${glow}` },
    { offset: FLASH_PEAK_MS / PEEK_FLASH_MS, outlineColor: color, boxShadow: `0 0 34px 10px ${glow}` },
    { offset: 1, outlineColor: 'transparent', boxShadow: `0 0 0 0 ${glow}` },
  ], { duration: PEEK_FLASH_MS, fill: 'forwards', easing: 'linear' })
  return anim.finished.catch(() => {})
}

// Bead travel along one connector: a LOCAL animation on the connector's own
// box, in percentage (left/top 0%→100%) — works the same whether the
// connector is a flat line (desktop row) or a standing one (narrow stack),
// without knowing which. The line itself tints and holds, same logic as a
// block (reset at the top of the next lap).
function travelConnector(wrap, bead, color) {
  if (!wrap) return Promise.resolve()
  cancelAnim(wrap)
  cancelAnim(bead)
  const beadAnim = bead?.animate([
    { offset: 0, left: '0%', top: '0%', opacity: 0 },
    { offset: 0.12, left: '0%', top: '0%', opacity: 1 },
    { offset: 0.88, opacity: 1 },
    { offset: 1, left: '100%', top: '100%', opacity: 0 },
  ], { duration: TRAVEL_MS, fill: 'forwards', easing: 'linear' })
  const lineAnim = wrap.animate([
    { offset: 0, backgroundColor: 'var(--color-border)' },
    { offset: 1, backgroundColor: color },
  ], { duration: TRAVEL_MS, fill: 'forwards', easing: 'linear' })
  return Promise.all([beadAnim?.finished.catch(() => {}), lineAnim.finished.catch(() => {})])
}

function StageIcon({ kind }) {
  switch (kind) {
    case 'bronze':
    case 'silver':
    case 'gold':
      return <img className="pipeline-container__icon-img" src="/logos/azure/storage-container.svg" alt="" aria-hidden="true" />
    case 'api':
      return <img className="pipeline-container__icon-img" src="/logos/azure/function-apps.svg" alt="" aria-hidden="true" />
    case 'dashboard':
      return <img className="pipeline-container__icon-img" src="/logos/azure/dashboard.svg" alt="" aria-hidden="true" />
    default:
      return null
  }
}

function ServiceCard({ icon, title, stack, children }) {
  return (
    <div className="pipeline-store">
      <p className="pipeline-store__head">
        <span className="pipeline-store__icon"><img src={icon} alt="" aria-hidden="true" /></span>
        <span className="pipeline-store__title">{title}</span>
      </p>
      <ul className={'pipeline-store__list' + (stack ? ' pipeline-store__list--stack' : '')}>
        {children}
      </ul>
    </div>
  )
}

function Layer({ kind, label, source, muted, containerRef, peekRef, wide, onClick }) {
  const preview = source.previews[kind]
  const className = 'pipeline-container' + (wide ? ' pipeline-container--wide' : '') + (onClick ? ' pipeline-container--link' : '')
  const container = onClick
    ? <button type="button" ref={containerRef} className={className} data-layer={kind} onClick={onClick} title="Aller au dashboard">
        <StageIcon kind={kind} /><span className="pipeline-container__name">{label}</span>
      </button>
    : <span ref={containerRef} className={className} data-layer={kind}>
        <StageIcon kind={kind} /><span className="pipeline-container__name">{label}</span>
      </span>

  return (
    <li className={'pipeline-layer' + (muted ? ' pipeline-layer--muted' : '')}>
      {container}
      {preview && (
        <div ref={peekRef} className="pipeline-peek">
          <PreviewPanel source={source} stageKind={kind} />
        </div>
      )}
    </li>
  )
}

function Connector({ cableKey, wrapRef, beadRef }) {
  const [open, setOpen] = useState(false)
  const note = cableKey && CABLE_NOTES[cableKey]
  return (
    <div ref={wrapRef} className="pipeline-connector">
      <i ref={beadRef} className="pipeline-bead" aria-hidden="true" />
      {note && (
        <button type="button" className="pipeline-connector__note-toggle" onClick={() => setOpen(o => !o)} aria-expanded={open} title={note.label}>i</button>
      )}
      {note && open && (
        <div className="pipeline-connector__note" role="note">
          <strong>{note.label}</strong>
          <p>{note.text}</p>
        </div>
      )}
    </div>
  )
}

function InlineConnector({ wrapRef, beadRef }) {
  return (
    <div ref={wrapRef} className="pipeline-connector pipeline-connector--inline">
      <i ref={beadRef} className="pipeline-bead" aria-hidden="true" />
    </div>
  )
}

export function PipelineDiagram() {
  const [selectedId, setSelectedId] = useState(SOURCES[0].id)
  const [swapping, setSwapping] = useState(false)
  const reducedMotion = usePrefersReducedMotion()
  const navigate = useNavigate()

  const source = SOURCES.find(s => s.id === selectedId)

  const sourceRefs = useRef({})
  const containerRefs = useRef({ bronze: null, silver: null, gold: null, api: null, dashboard: null })
  const peekRefs = useRef({ bronze: null, silver: null, gold: null, api: null })
  // 5 connectors: src→bronze, bronze→silver, silver→gold, gold→api, api→dashboard
  const connWrapRefs = useRef([null, null, null, null, null])
  const connBeadRefs = useRef([null, null, null, null, null])

  useEffect(() => {
    setSwapping(true)
    const t = setTimeout(() => setSwapping(false), 200)
    return () => clearTimeout(t)
  }, [selectedId])

  useEffect(() => {
    const allNodes = Object.values(sourceRefs.current)
    const allContainers = Object.values(containerRefs.current)
    const allPeeks = Object.values(peekRefs.current)
    const allWraps = connWrapRefs.current
    const allBeads = connBeadRefs.current

    if (reducedMotion) {
      allNodes.forEach(cancelAnim); allContainers.forEach(cancelAnim); allPeeks.forEach(cancelAnim)
      allWraps.forEach(cancelAnim); allBeads.forEach(cancelAnim)
      const { color } = source
      const node = sourceRefs.current[selectedId]
      if (node) { node.style.outlineColor = color; node.style.boxShadow = 'none' }
      for (let i = 0; i < source.visitedCount; i++) {
        const kind = STAGE_KINDS[i]
        const c = containerRefs.current[kind]
        if (c) { c.style.outlineColor = color; c.style.boxShadow = 'none' }
        const w = connWrapRefs.current[i]
        if (w) w.style.backgroundColor = color
      }
      return
    }

    let cancelled = false

    async function run() {
      allNodes.forEach(cancelAnim); allContainers.forEach(cancelAnim); allPeeks.forEach(cancelAnim)
      allWraps.forEach(cancelAnim); allBeads.forEach(cancelAnim)

      const { color, glow } = source
      await lightNode(sourceRefs.current[selectedId], color, glow)
      if (cancelled) return

      for (let i = 0; i < source.visitedCount; i++) {
        await travelConnector(connWrapRefs.current[i], connBeadRefs.current[i], color)
        if (cancelled) return
        const kind = STAGE_KINDS[i]
        const tasks = [lightNode(containerRefs.current[kind], color, glow)]
        if (peekRefs.current[kind]) tasks.push(flashPeek(peekRefs.current[kind], color, glow))
        await Promise.all(tasks)
        if (cancelled) return
      }

      await sleep(LOOP_PAUSE_MS)
      if (cancelled) return
      const idx = SOURCES.findIndex(s => s.id === selectedId)
      setSelectedId(SOURCES[(idx + 1) % SOURCES.length].id)
    }
    run()

    return () => {
      cancelled = true
      allNodes.forEach(cancelAnim); allContainers.forEach(cancelAnim); allPeeks.forEach(cancelAnim)
      allWraps.forEach(cancelAnim); allBeads.forEach(cancelAnim)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, reducedMotion])

  return (
    <div className="pipeline-diagram">
      <p className={'pipeline-lede' + (swapping ? ' pipeline-lede--swapping' : '')}>
        {source.lede.map((seg, i) => (seg.cls ? <span key={i} className={'pipeline-lede__' + seg.cls}>{seg.text}</span> : seg.text))}
      </p>

      <div className="pipeline-scene">
        <div className="pipeline-scene__row">
          <div className="pipeline-sources" role="tablist" aria-label="Choisir une source">
            {SOURCES.map(s => (
              <button
                key={s.id}
                type="button"
                ref={el => { sourceRefs.current[s.id] = el }}
                className={'pipeline-node' + (s.id === selectedId ? ' pipeline-node--active' : '')}
                style={{ '--pipeline-src': s.color }}
                onClick={() => setSelectedId(s.id)}
                aria-pressed={s.id === selectedId}
              >
                <span className="pipeline-node__body">
                  <span className="pipeline-node__dot" aria-hidden="true" />
                  <span className="pipeline-node__icon" aria-hidden="true">
                    <img className="pipeline-node__icon-img pipeline-node__icon-img--light" src={s.logo} alt="" />
                    <img className="pipeline-node__icon-img pipeline-node__icon-img--dark" src={s.logoDark || s.logo} alt="" />
                  </span>
                  <span className="pipeline-node__title">{s.label}</span>
                </span>
              </button>
            ))}
          </div>

          <Connector wrapRef={el => { connWrapRefs.current[0] = el }} beadRef={el => { connBeadRefs.current[0] = el }} />

          <ServiceCard icon="/logos/azure/storage-accounts.svg" title="ADLS Gen 2" stack>
            <Layer kind="bronze" label="Bronze" source={source} muted={source.visitedCount < 1}
              containerRef={el => { containerRefs.current.bronze = el }} peekRef={el => { peekRefs.current.bronze = el }} />
            <InlineConnector wrapRef={el => { connWrapRefs.current[1] = el }} beadRef={el => { connBeadRefs.current[1] = el }} />
            <Layer kind="silver" label="Silver" source={source} muted={source.visitedCount < 2}
              containerRef={el => { containerRefs.current.silver = el }} peekRef={el => { peekRefs.current.silver = el }} />
          </ServiceCard>

          <Connector cableKey="cleaning" wrapRef={el => { connWrapRefs.current[2] = el }} beadRef={el => { connBeadRefs.current[2] = el }} />
          <ServiceCard icon="/logos/azure/sql-server.svg" title="SQL Server">
            <Layer kind="gold" label="Gold" source={source} muted={source.visitedCount < 3}
              containerRef={el => { containerRefs.current.gold = el }} peekRef={el => { peekRefs.current.gold = el }} />
          </ServiceCard>

          <Connector cableKey="aggregation" wrapRef={el => { connWrapRefs.current[3] = el }} beadRef={el => { connBeadRefs.current[3] = el }} />
          <ServiceCard icon="/logos/azure/function-apps.svg" title="Function App">
            <Layer kind="api" label="Endpoints" source={source} muted={source.visitedCount < 4}
              containerRef={el => { containerRefs.current.api = el }} peekRef={el => { peekRefs.current.api = el }} />
          </ServiceCard>

          <Connector wrapRef={el => { connWrapRefs.current[4] = el }} beadRef={el => { connBeadRefs.current[4] = el }} />
          <ServiceCard icon="/logos/azure/static-web-apps.svg" title="Static Web Apps">
            <Layer kind="dashboard" label="Dashboard" source={source} muted={source.visitedCount < 5} wide
              containerRef={el => { containerRefs.current.dashboard = el }} onClick={() => navigate('/')} />
          </ServiceCard>
        </div>
      </div>

      <p className="pipeline-source-links">
        Liens des sources : {SOURCES.map((s, i) => (
          <span key={s.id}>
            {i > 0 && ' · '}
            <a href={s.homepage} target="_blank" rel="noopener noreferrer">{s.label}</a>
          </span>
        ))}
      </p>
    </div>
  )
}
