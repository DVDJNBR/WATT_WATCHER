/**
 * PipelineDiagram — the data journey as a source-by-source animation.
 *
 * Horizontal row of stage columns spanning the full width — Bronze/Silver
 * (grouped as the data lake), Gold, API, Dashboard — each with its own
 * always-visible example underneath (JSON / parquet-row / table-row / route
 * name). Below a width breakpoint the row becomes a vertical stack instead
 * of scrolling sideways.
 *
 * Pick a source; a spark travels Bronze → Silver → Gold → API → Dashboard
 * (most sources) or stops at Gold (ENTSO-E prices, no live API route yet).
 * Each arrival lights up that stage's own example panel below it.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SOURCES, STAGES, CABLE_NOTES } from '../../data/pipelineSources.js'
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion.js'
import { PreviewPanel } from './PreviewPanel.jsx'

const DEFAULT_DWELL_MS = 1700
const TRAVEL_MS = 700
const ARRIVE_PULSE_MS = 550

function StageIcon({ kind }) {
  switch (kind) {
    case 'bronze':
      return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M4 8h16M4 8v10a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V8M4 8l2-4h12l2 4" strokeLinecap="round" strokeLinejoin="round" /></svg>
    case 'silver':
      return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M4 6h6M4 10h4M4 14h6M4 18h4" /><path d="M13 6h7v12h-7z" /></svg>
    case 'gold':
      return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="6" rx="7" ry="2.5" /><path d="M5 6v6c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V6" /><path d="M5 12v6c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-6" /></svg>
    case 'api':
      return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M8 4 3 12l5 8M16 4l5 8-5 8" /></svg>
    default:
      return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="19" x2="5" y2="11" /><line x1="12" y1="19" x2="12" y2="5" /><line x1="19" y1="19" x2="19" y2="14" /></svg>
  }
}

function StageNode({ stage, visited, current, arriving, source, onDashboardClick }) {
  const isDashboard = stage.kind === 'dashboard'
  const style = current ? { '--stage-color': source.color, '--stage-glow': source.glow } : undefined

  const content = (
    <>
      <span className="pipeline-stage__glow" aria-hidden="true" />
      <span className="pipeline-stage__icon"><StageIcon kind={stage.kind} /></span>
      <span className="pipeline-stage__label">{stage.label}</span>
      <span className="pipeline-stage__sub">{stage.sub}</span>
    </>
  )

  const className = 'pipeline-stage'
    + (visited ? '' : ' pipeline-stage--muted')
    + (current ? ' pipeline-stage--current' : '')
    + (arriving ? ' pipeline-stage--arriving' : '')
    + (isDashboard ? ' pipeline-stage--link' : '')

  if (isDashboard) {
    return (
      <button type="button" className={className} style={style} onClick={onDashboardClick} title="Aller au dashboard">
        {content}
      </button>
    )
  }
  return <div className={className} style={style}>{content}</div>
}

function Connector({ traveled, spark, source, cableKey }) {
  const [open, setOpen] = useState(false)
  const note = cableKey && CABLE_NOTES[cableKey]
  const style = traveled ? { '--stage-color': source.color, '--stage-glow': source.glow } : undefined

  return (
    <div
      className={'pipeline-connector'
        + (traveled ? ' pipeline-connector--traveled' : '')
        + (spark ? ' pipeline-connector--spark' : '')}
      style={style}
    >
      <span className="pipeline-connector__line" aria-hidden="true" />
      {spark && (
        <span
          className="pipeline-connector__spark"
          style={{ '--travel-duration': `${TRAVEL_MS}ms` }}
          aria-hidden="true"
        />
      )}
      {note && (
        <button
          type="button"
          className="pipeline-connector__note-toggle"
          onClick={() => setOpen(o => !o)}
          aria-expanded={open}
          title={note.label}
        >
          i
        </button>
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

/** A stage node plus its always-visible example, stacked — one column of the flow. */
function PipelineColumn({ stage, visited, current, arriving, source, onDashboardClick }) {
  return (
    <div className={'pipeline-column' + (visited ? '' : ' pipeline-column--muted')}>
      <StageNode stage={stage} visited={visited} current={current} arriving={arriving} source={source} onDashboardClick={onDashboardClick} />
      <div
        className={'pipeline-column__example' + (arriving ? ' pipeline-column__example--lit' : '')}
        style={{ '--stage-color': source.color, '--stage-glow': source.glow }}
      >
        <PreviewPanel source={source} stageKind={stage.kind} />
      </div>
    </div>
  )
}

function SourceToggle({ source, active, onSelect }) {
  return (
    <button
      type="button"
      className={'source-toggle' + (active ? ' source-toggle--active' : '')}
      style={{ '--source-color': source.color, '--source-glow': source.glow }}
      onClick={() => onSelect(source.id)}
      aria-pressed={active}
    >
      <span className="source-toggle__dot" aria-hidden="true" />
      {source.label}
    </button>
  )
}

export function PipelineDiagram() {
  const [selectedId, setSelectedId] = useState(SOURCES[0].id)
  const [stageIndex, setStageIndex] = useState(0)
  const [travelingConnector, setTravelingConnector] = useState(null)
  const [arrivingIndex, setArrivingIndex] = useState(null)
  const reducedMotion = usePrefersReducedMotion()
  const navigate = useNavigate()
  const timeoutsRef = useRef([])

  const source = SOURCES.find(s => s.id === selectedId)

  useEffect(() => {
    if (reducedMotion) {
      setStageIndex(source.visitedCount - 1)
      setTravelingConnector(null)
      setArrivingIndex(null)
      return
    }
    let cancelled = false
    const schedule = (fn, ms) => {
      const t = setTimeout(() => { if (!cancelled) fn() }, ms)
      timeoutsRef.current.push(t)
    }

    function arriveAt(i) {
      setStageIndex(i)
      setTravelingConnector(null)
      setArrivingIndex(i)
      schedule(() => setArrivingIndex(null), ARRIVE_PULSE_MS)
      if (i < source.visitedCount - 1) {
        const dwell = source.dwell?.[i] ?? DEFAULT_DWELL_MS
        schedule(() => travelTo(i + 1), dwell)
      }
    }
    function travelTo(i) {
      setTravelingConnector(i - 1)
      schedule(() => arriveAt(i), TRAVEL_MS)
    }

    arriveAt(0)

    return () => {
      cancelled = true
      timeoutsRef.current.forEach(clearTimeout)
      timeoutsRef.current = []
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, reducedMotion])

  const columnProps = i => ({
    stage: STAGES[i],
    visited: i < source.visitedCount,
    current: stageIndex === i,
    arriving: arrivingIndex === i,
    source,
  })

  return (
    <div className="pipeline-diagram">
      <div className="pipeline-source-row" role="tablist" aria-label="Choisir une source">
        {SOURCES.map(s => (
          <SourceToggle key={s.id} source={s} active={s.id === selectedId} onSelect={setSelectedId} />
        ))}
      </div>

      {source.note && <p className="pipeline-diagram__source-note">{source.note}</p>}

      <div className="pipeline-flow">
        <div className="pipeline-flow__group">
          <span className="data-lake-group__label">Data lake — ADLS Gen2</span>
          <div className="pipeline-flow__row">
            <PipelineColumn {...columnProps(0)} />
            <Connector traveled={stageIndex >= 1 || travelingConnector === 0} spark={travelingConnector === 0} source={source} cableKey="cleaning" />
            <PipelineColumn {...columnProps(1)} />
          </div>
        </div>

        <Connector traveled={stageIndex >= 2 || travelingConnector === 1} spark={travelingConnector === 1} source={source} cableKey="aggregation" />
        <PipelineColumn {...columnProps(2)} />
        <Connector traveled={(stageIndex >= 3 && 3 < source.visitedCount) || travelingConnector === 2} spark={travelingConnector === 2} source={source} />
        <PipelineColumn {...columnProps(3)} />
        <Connector traveled={(stageIndex >= 4 && 4 < source.visitedCount) || travelingConnector === 3} spark={travelingConnector === 3} source={source} />
        <PipelineColumn {...columnProps(4)} onDashboardClick={() => navigate('/')} />
      </div>
    </div>
  )
}
