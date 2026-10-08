/**
 * PipelineDiagram — a direct port of the VALIDATED mockup:
 * app_v2/mockups/pipeline-block.pre-css-rewrite.bak.html (not the later
 * full-CSS-rewrite sibling file, which this component used to be ported
 * from by mistake — wrong geometry, wrong preview placement, wrong font
 * scale, hence the layout bugs this rewrite fixes).
 *
 * Fixed 1150px geometry: five source tiles, four Azure service cards at
 * hand-tuned widths (ADLS 388 / SQL 196 / Function App 205 / Static Web
 * Apps 150 + gaps) that sum to exactly 1150px — see the mockup's own
 * comment block for the arithmetic. Data previews live in a separate strip
 * BELOW the row, each absolutely positioned so its centre falls under the
 * column it illustrates, not inline next to its chip.
 *
 * Connector paths are real: a single SVG layer whose `d` is computed from
 * every block's measured position (`measureScene`/`layoutChains`, ported
 * near-verbatim from the mockup's vanilla-JS functions of the same name) —
 * never hard-coded coordinates, because those drift the moment an icon,
 * font, or label changes. The bead travels one real segment at a time
 * (`travelBead`), its duration from actual on-screen distance (`SPEED`
 * px/s) rather than a fixed-but-arbitrary one, exactly like the mockup.
 *
 * Deliberately NOT responsive past the horizontal-scroll fallback in CSS:
 * the mockup scoped true responsiveness as separate future work, and a
 * fixed-pixel diagram that reflows per block size is a different, bigger
 * component than this one.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SOURCES } from '../../data/pipelineSources.js'
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion.js'
import { JsonBlock } from '../JsonBlock.jsx'

const SPEED = 46          // px/s — bead travel speed, real distance ÷ this = duration
const FLASH_PEAK = 0.25   // s — halo rise to peak
const FLASH_SETTLE = 0.45 // s — peak to held-full (blocks)
const FLASH_DECAY = 0.75  // s — peak to neutral (previews)
const LOOP_PAUSE = 0.4    // s — pause after Dashboard, before the next source

// Tile id → flow-color slug.
const FLOW_SLUG = {
  'rte-production': 'rte',
  'open-meteo': 'meteo',
  'odre-capacity': 'capacity',
  'entsoe-price': 'price',
}

function rectIn(el, origin) {
  const b = el.getBoundingClientRect()
  return { l: b.left - origin.left, r: b.right - origin.left, cy: b.top - origin.top + b.height / 2 }
}
function pathD(a, b) { return `M${a.x} ${a.y}L${b.x} ${b.y}` }
function dist(a, b) { return Math.hypot(b.x - a.x, b.y - a.y) }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }
function cancelAnim(el) { if (el) el.getAnimations().forEach(a => a.cancel()) }

// Cancelling a `fill:forwards` animation should be enough on its own to
// drop an element back to its stylesheet default — but belt-and-suspenders
// against any WAAPI edge case that leaves a held color behind lap to lap:
// also clear the inline properties `lightNode`/`flashPeek` ever touch.
function hardReset(el) {
  if (!el) return
  cancelAnim(el)
  el.style.removeProperty('outline-color')
  el.style.removeProperty('box-shadow')
}

function flowColors(scene, slug) {
  const cs = getComputedStyle(scene)
  return {
    flow: cs.getPropertyValue(`--color-source-${slug}`).trim(),
    soft: cs.getPropertyValue(`--flow-${slug}-soft`).trim(),
    gone: cs.getPropertyValue(`--flow-${slug}-gone`).trim(),
  }
}

// Contour of a block: the whole outline lights at once, peaks through a
// wide halo, then STAYS lit — a trace of the pass, reset at the top of the
// next lap.
function lightNode(el, colors) {
  if (!el) return Promise.resolve()
  cancelAnim(el)
  const total = FLASH_PEAK + FLASH_SETTLE
  const anim = el.animate([
    { offset: 0, outlineColor: 'transparent', boxShadow: `0 0 0 0 ${colors.gone}` },
    { offset: FLASH_PEAK / total, outlineColor: colors.flow, boxShadow: `0 0 26px 8px ${colors.soft}` },
    { offset: 1, outlineColor: colors.flow, boxShadow: `0 0 0 0 ${colors.gone}` },
  ], { duration: total * 1000, fill: 'forwards', easing: 'linear' })
  return anim.finished.catch(() => {})
}

// Halo of a data preview: lights, peaks, decays back to neutral — a
// preview shows what the data just BECAME, not where it is, so unlike a
// block it must not stay lit. Takes a list: Gold flashes fact + up to 3
// dims together.
function flashPeek(els, colors) {
  const list = (Array.isArray(els) ? els : [els]).filter(Boolean)
  if (!list.length) return Promise.resolve()
  const total = FLASH_PEAK + FLASH_DECAY
  return Promise.all(list.map(el => {
    cancelAnim(el)
    const anim = el.animate([
      { offset: 0, outlineColor: 'transparent', boxShadow: `0 0 0 0 ${colors.gone}` },
      { offset: FLASH_PEAK / total, outlineColor: colors.flow, boxShadow: `0 0 34px 10px ${colors.soft}` },
      { offset: 1, outlineColor: 'transparent', boxShadow: `0 0 0 0 ${colors.gone}` },
    ], { duration: total * 1000, fill: 'forwards', easing: 'linear' })
    return anim.finished.catch(() => {})
  }))
}

// One travel segment: bead + its trail, both driven by the real measured
// distance so a long diagonal takes visibly longer than a short hop.
function travelBead(bead, trailEl, from, to, colors) {
  const len = dist(from, to)
  const durSec = Math.max(0.15, len / SPEED)
  trailEl.setAttribute('d', pathD(from, to))
  trailEl.style.stroke = colors.flow
  cancelAnim(trailEl)
  const totalLen = trailEl.getTotalLength()
  trailEl.style.strokeDasharray = String(totalLen)
  const trailAnim = trailEl.animate(
    [{ strokeDashoffset: totalLen }, { strokeDashoffset: 0 }],
    { duration: durSec * 1000, fill: 'forwards', easing: 'linear' }
  )
  cancelAnim(bead)
  const edge = Math.min(0.4, 0.12 / durSec)
  const beadAnim = bead.animate([
    { offset: 0, transform: `translate(${from.x}px, ${from.y}px)`, opacity: 0 },
    { offset: edge, transform: `translate(${from.x}px, ${from.y}px)`, opacity: 1 },
    { offset: 1 - edge, opacity: 1 },
    { offset: 1, transform: `translate(${to.x}px, ${to.y}px)`, opacity: 0 },
  ], { duration: durSec * 1000, fill: 'forwards', easing: 'linear' })
  return Promise.all([trailAnim.finished.catch(() => {}), beadAnim.finished.catch(() => {})])
}

function measureScene(refs) {
  const scene = refs.sceneRef.current.getBoundingClientRect()
  const R = el => rectIn(el, scene)
  const geo = { tiles: {} }
  for (const id of Object.keys(refs.tileRefs.current)) {
    geo.tiles[id] = R(refs.tileRefs.current[id])
  }
  geo.bronze = R(refs.bronzeRef.current)
  geo.silver = R(refs.silverRef.current)
  geo.gold = R(refs.goldRef.current)
  geo.fn = R(refs.fnRef.current)
  geo.swa = R(refs.swaRef.current)
  geo.rowCy = geo.bronze.cy
  return geo
}

function layoutChains(geo, refs) {
  for (const [id, box] of Object.entries(geo.tiles)) {
    const el = refs.tileChainRefs.current[id]
    if (el) el.setAttribute('d', pathD({ x: box.r, y: box.cy }, { x: geo.bronze.l, y: geo.rowCy }))
  }
  const fixed = [
    [refs.chainBronzeSilverRef, geo.bronze, geo.silver],
    [refs.chainSilverGoldRef, geo.silver, geo.gold],
    [refs.chainGoldFnRef, geo.gold, geo.fn],
    [refs.chainFnSwaRef, geo.fn, geo.swa],
  ]
  for (const [ref, a, b] of fixed) {
    if (ref.current) ref.current.setAttribute('d', pathD({ x: a.r, y: geo.rowCy }, { x: b.l, y: geo.rowCy }))
  }
}

function StageIcon({ kind }) {
  switch (kind) {
    case 'bronze':
    case 'silver':
    case 'gold':
      return <img className="pipeline-container__icon-img" src="/logos/azure/storage-container.svg" alt="" aria-hidden="true" />
    case 'fn':
      return <img className="pipeline-container__icon-img" src="/logos/azure/function-apps.svg" alt="" aria-hidden="true" />
    case 'app':
      return <img className="pipeline-container__icon-img" src="/logos/azure/dashboard.svg" alt="" aria-hidden="true" />
    default:
      return null
  }
}

function MiniTable({ innerRef, table, columns, row, caption = false }) {
  return (
    <table ref={innerRef} className="pipeline-table">
      {caption && <caption>{table}</caption>}
      <tbody>
        {columns.map((c, i) => (
          <tr key={c}>
            <th scope="row">{c}</th>
            <td>{String(row[i])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// Normalizes Gold's two shapes (star schema vs. a plain fact table, for
// sources with no dimensions worth drawing) to one `{table, columns, row}`
// the preview strip can render the same way.
function factOf(gold) {
  return gold.kind === 'star' ? gold.fact : gold
}

export function PipelineDiagram() {
  const [selectedId, setSelectedId] = useState(SOURCES[0].id)
  const [swapping, setSwapping] = useState(false)
  const reducedMotion = usePrefersReducedMotion()
  const navigate = useNavigate()

  const source = SOURCES.find(s => s.id === selectedId)
  const gold = source.previews.gold
  const fact = factOf(gold)
  const goldExtra = gold.kind === 'star' ? (gold.extra || []) : []
  const dim1 = gold.kind === 'star' ? gold.dim1 : null
  const dim2 = gold.kind === 'star' ? gold.dim2 : null
  const dim3 = gold.kind === 'star' ? gold.dim3 : null

  const sceneRef = useRef(null)
  const tileRefs = useRef({})
  const tileChainRefs = useRef({})
  const bronzeRef = useRef(null)
  const silverRef = useRef(null)
  const goldRef = useRef(null)
  const fnRef = useRef(null)
  const swaRef = useRef(null)
  const chainBronzeSilverRef = useRef(null)
  const chainSilverGoldRef = useRef(null)
  const chainGoldFnRef = useRef(null)
  const chainFnSwaRef = useRef(null)
  const trailSrcBronzeRef = useRef(null)
  const trailBronzeSilverRef = useRef(null)
  const trailSilverGoldRef = useRef(null)
  const trailGoldFnRef = useRef(null)
  const trailFnSwaRef = useRef(null)
  const beadRef = useRef(null)
  const bronzeInnerRefs = useRef([])
  const silverInnerRefs = useRef([])
  const factInnerRef = useRef(null)
  const factExtraInnerRefs = useRef([])
  const dim1InnerRef = useRef(null)
  const dim2InnerRef = useRef(null)
  const dim3InnerRef = useRef(null)
  const apiInnerRef = useRef(null)

  const refs = {
    sceneRef, tileRefs, tileChainRefs, bronzeRef, silverRef, goldRef, fnRef, swaRef,
    chainBronzeSilverRef, chainSilverGoldRef, chainGoldFnRef, chainFnSwaRef,
  }

  useEffect(() => {
    setSwapping(true)
    const t = setTimeout(() => setSwapping(false), 200)
    return () => clearTimeout(t)
  }, [selectedId])

  useEffect(() => {
    const allAnimated = [
      ...Object.values(tileRefs.current), bronzeRef.current, silverRef.current, goldRef.current, fnRef.current, swaRef.current,
      ...bronzeInnerRefs.current, ...silverInnerRefs.current, factInnerRef.current, ...factExtraInnerRefs.current,
      dim1InnerRef.current, dim2InnerRef.current, dim3InnerRef.current, apiInnerRef.current,
    ]
    const trails = [trailSrcBronzeRef.current, trailBronzeSilverRef.current, trailSilverGoldRef.current, trailGoldFnRef.current, trailFnSwaRef.current]

    const geo = measureScene(refs)
    layoutChains(geo, refs)
    const slug = FLOW_SLUG[selectedId]
    const scene = sceneRef.current
    const colors = flowColors(scene, slug)

    const stopsAll = [
      { enter: { x: geo.tiles[selectedId].r, y: geo.tiles[selectedId].cy }, exit: { x: geo.tiles[selectedId].r, y: geo.tiles[selectedId].cy }, el: tileRefs.current[selectedId] },
      { enter: { x: geo.bronze.l, y: geo.rowCy }, exit: { x: geo.bronze.r, y: geo.rowCy }, el: bronzeRef.current },
      { enter: { x: geo.silver.l, y: geo.rowCy }, exit: { x: geo.silver.r, y: geo.rowCy }, el: silverRef.current },
      { enter: { x: geo.gold.l, y: geo.rowCy }, exit: { x: geo.gold.r, y: geo.rowCy }, el: goldRef.current },
      { enter: { x: geo.fn.l, y: geo.rowCy }, exit: { x: geo.fn.r, y: geo.rowCy }, el: fnRef.current },
      { enter: { x: geo.swa.l, y: geo.rowCy }, exit: { x: geo.swa.r, y: geo.rowCy }, el: swaRef.current },
    ]
    const steps = Math.min(source.visitedCount, 5)

    if (reducedMotion) {
      allAnimated.forEach(hardReset)
      const tile = tileRefs.current[selectedId]
      if (tile) { tile.style.outlineColor = colors.flow; tile.style.boxShadow = 'none' }
      for (let i = 0; i < steps; i++) {
        const el = stopsAll[i + 1].el
        if (el) { el.style.outlineColor = colors.flow; el.style.boxShadow = 'none' }
      }
      trails.forEach((el, i) => {
        if (!el) return
        if (i < steps) {
          el.setAttribute('d', pathD(stopsAll[i].exit, stopsAll[i + 1].enter))
          el.style.stroke = colors.flow
          el.style.strokeDashoffset = 0
        } else {
          el.style.strokeDasharray = '0'
        }
      })
      return
    }

    let cancelled = false
    async function run() {
      allAnimated.forEach(hardReset)
      trails.forEach(el => {
        cancelAnim(el)
        if (el && el.getAttribute('d')) el.style.strokeDashoffset = String(el.getTotalLength())
      })
      cancelAnim(beadRef.current)

      await lightNode(stopsAll[0].el, colors)
      if (cancelled) return

      const trailRefsArr = [trailSrcBronzeRef, trailBronzeSilverRef, trailSilverGoldRef, trailGoldFnRef, trailFnSwaRef]
      const peekTargets = [
        null,
        () => bronzeInnerRefs.current,
        () => silverInnerRefs.current,
        () => [factInnerRef.current, ...factExtraInnerRefs.current, dim1InnerRef.current, dim2InnerRef.current, dim3InnerRef.current],
        () => apiInnerRef.current,
        null,
      ]

      for (let i = 0; i < steps; i++) {
        await travelBead(beadRef.current, trailRefsArr[i].current, stopsAll[i].exit, stopsAll[i + 1].enter, colors)
        if (cancelled) return
        const tasks = [lightNode(stopsAll[i + 1].el, colors)]
        const targetFn = peekTargets[i + 1]
        if (targetFn) tasks.push(flashPeek(targetFn(), colors))
        await Promise.all(tasks)
        if (cancelled) return
      }

      await sleep(LOOP_PAUSE * 1000)
      if (cancelled) return
      const idx = SOURCES.findIndex(s => s.id === selectedId)
      setSelectedId(SOURCES[(idx + 1) % SOURCES.length].id)
    }
    run()

    return () => {
      cancelled = true
      allAnimated.forEach(hardReset)
      trails.forEach(cancelAnim)
      cancelAnim(beadRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, reducedMotion])

  return (
    <div className="pipeline-diagram">
      <p className={'pipeline-lede' + (swapping ? ' pipeline-lede--swapping' : '')}>
        {source.lede.map((seg, i) => (seg.cls ? <span key={i} className={'pipeline-lede__' + seg.cls}>{seg.text}</span> : seg.text))}
      </p>

      <div className="pipeline-scene-scroll">
        <div className="pipeline-scene" ref={sceneRef}>
          <svg className="pipeline-flow" viewBox="0 0 1150 450" fill="none" aria-hidden="true">
            {SOURCES.map(s => (
              <path
                key={s.id}
                ref={el => { tileChainRefs.current[s.id] = el }}
                className={'pipeline-chain pipeline-chain--src' + (s.id === selectedId ? ' is-active' : '') + ' pipeline-chain--' + FLOW_SLUG[s.id]}
              />
            ))}
            <path ref={chainBronzeSilverRef} className="pipeline-chain" />
            <path ref={chainSilverGoldRef} className="pipeline-chain" />
            <path ref={chainGoldFnRef} className="pipeline-chain" />
            <path ref={chainFnSwaRef} className="pipeline-chain" />
            <path ref={trailSrcBronzeRef} className="pipeline-chain--trail" />
            <path ref={trailBronzeSilverRef} className="pipeline-chain--trail" />
            <path ref={trailSilverGoldRef} className="pipeline-chain--trail" />
            <path ref={trailGoldFnRef} className="pipeline-chain--trail" />
            <path ref={trailFnSwaRef} className="pipeline-chain--trail" />
          </svg>
          <div className="pipeline-beads" aria-hidden="true">
            <i ref={beadRef} className="pipeline-bead" />
          </div>

          <div className="pipeline-scene__row">
            <div className="pipeline-sources" role="tablist" aria-label="Choisir une source">
              {SOURCES.map(s => (
                <button
                  key={s.id}
                  type="button"
                  ref={el => { tileRefs.current[s.id] = el }}
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

            <div className="pipeline-gap pipeline-gap--bus" />

            <div className="pipeline-store pipeline-store--adls">
              <p className="pipeline-store__head">
                <span className="pipeline-store__icon"><img src="/logos/azure/storage-accounts.svg" alt="" aria-hidden="true" /></span>
                <span className="pipeline-store__title">ADLS Gen 2</span>
              </p>
              <ul className="pipeline-store__list">
                <li>
                  <span ref={bronzeRef} className="pipeline-container" data-layer="bronze">
                    <StageIcon kind="bronze" /><span className="pipeline-container__name">Bronze</span>
                  </span>
                </li>
                <li>
                  <span ref={silverRef} className="pipeline-container" data-layer="silver">
                    <StageIcon kind="silver" /><span className="pipeline-container__name">Silver</span>
                  </span>
                </li>
              </ul>
            </div>

            <div className="pipeline-gap" />

            <div className="pipeline-store pipeline-store--sql">
              <p className="pipeline-store__head">
                <span className="pipeline-store__icon"><img src="/logos/azure/sql-server.svg" alt="" aria-hidden="true" /></span>
                <span className="pipeline-store__title">SQL Server</span>
              </p>
              <ul className="pipeline-store__list">
                <li>
                  <span ref={goldRef} className="pipeline-container" data-layer="gold">
                    <StageIcon kind="gold" /><span className="pipeline-container__name">Gold</span>
                  </span>
                </li>
              </ul>
            </div>

            <div className="pipeline-gap" />

            <div className="pipeline-store pipeline-store--fn">
              <p className="pipeline-store__head">
                <span className="pipeline-store__icon"><img src="/logos/azure/function-apps.svg" alt="" aria-hidden="true" /></span>
                <span className="pipeline-store__title">Function App</span>
              </p>
              <ul className="pipeline-store__list">
                <li>
                  <span ref={fnRef} className="pipeline-container" data-layer="fn">
                    <StageIcon kind="fn" /><span className="pipeline-container__name">Endpoints</span>
                  </span>
                </li>
              </ul>
            </div>

            <div className="pipeline-gap" />

            <div className="pipeline-store pipeline-store--swa">
              <p className="pipeline-store__head">
                <span className="pipeline-store__icon"><img src="/logos/azure/static-web-apps.svg" alt="" aria-hidden="true" /></span>
                <span className="pipeline-store__title">Static Web Apps</span>
              </p>
              <ul className="pipeline-store__list">
                <li>
                  <button
                    type="button"
                    ref={swaRef}
                    className="pipeline-container pipeline-container--wide pipeline-container--link"
                    data-layer="app"
                    onClick={() => navigate('/')}
                    title="Aller au dashboard"
                  >
                    <StageIcon kind="app" /><span className="pipeline-container__name">Dashboard</span>
                  </button>
                </li>
              </ul>
            </div>
          </div>

          <div className="pipeline-below">
            <svg className="pipeline-links" viewBox="0 -102 1150 352" fill="none" aria-hidden="true">
              <path d="M284 -76V22" stroke="currentColor" strokeWidth="1" />
              <path d="M476 -76V22" stroke="currentColor" strokeWidth="1" />
              <path d="M682 -76L616 22" stroke="currentColor" strokeWidth="1" />
              <path d="M887 -76L930 22" stroke="currentColor" strokeWidth="1" />
              {dim1 && <>
                <path d="M672 41L728 41" stroke="currentColor" strokeWidth="1" />
                <path d="M672 41L665.0 37.5M672 41L665.0 44.5" stroke="currentColor" strokeWidth="1" />
                <path d="M719.0 37.5L719.0 44.5" stroke="currentColor" strokeWidth="1" />
              </>}
              {dim2 && <>
                <path d="M672 54L728 101" stroke="currentColor" strokeWidth="1" />
                <path d="M672 54L668.9 46.8M672 54L664.4 52.2" stroke="currentColor" strokeWidth="1" />
                <path d="M723.4 92.5L718.9 97.9" stroke="currentColor" strokeWidth="1" />
              </>}
              {dim3 && <>
                <path d="M672 66L728 161" stroke="currentColor" strokeWidth="1" />
                <path d="M672 66L671.5 58.2M672 66L665.4 61.7" stroke="currentColor" strokeWidth="1" />
                <path d="M726.4 151.5L720.4 155.0" stroke="currentColor" strokeWidth="1" />
              </>}
            </svg>

            <div className="pipeline-peek pipeline-peek--bronze">
              {source.previews.bronze.map((p, i) => p.kind === 'csv'
                ? <pre key={i} ref={el => { bronzeInnerRefs.current[i] = el }} className="content-codeblock">{p.header}{'\n'}{p.row}</pre>
                : <JsonBlock key={i} ref={el => { bronzeInnerRefs.current[i] = el }} data={p.data} />)}
            </div>

            <div className="pipeline-peek pipeline-peek--silver">
              {source.previews.silver.map((p, i) => (
                <MiniTable key={i} innerRef={el => { silverInnerRefs.current[i] = el }} {...p} />
              ))}
            </div>

            <div className="pipeline-peek pipeline-peek--fact">
              <MiniTable innerRef={factInnerRef} {...fact} caption />
              {goldExtra.map((t, i) => (
                <MiniTable key={i} innerRef={el => { factExtraInnerRefs.current[i] = el }} {...t} caption />
              ))}
            </div>

            {dim1 && <div className="pipeline-peek pipeline-peek--dim1">
              <MiniTable innerRef={dim1InnerRef} {...dim1} caption />
            </div>}
            {dim2 && <div className="pipeline-peek pipeline-peek--dim2">
              <MiniTable innerRef={dim2InnerRef} {...dim2} caption />
            </div>}
            {dim3 && <div className="pipeline-peek pipeline-peek--dim3">
              <MiniTable innerRef={dim3InnerRef} {...dim3} caption />
            </div>}

            {source.previews.api.length > 0 && (
              <div className="pipeline-peek pipeline-peek--api">
                <pre ref={apiInnerRef} className="content-codeblock pipeline-route">
                  {source.previews.api.map((route, i) => {
                    const [verb, path] = route.split(' ')
                    return (
                      <span key={i} className="pipeline-route__line">
                        <span className="pipeline-http-verb">{verb}</span> {path}
                      </span>
                    )
                  })}
                </pre>
              </div>
            )}
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
      </div>
    </div>
  )
}
