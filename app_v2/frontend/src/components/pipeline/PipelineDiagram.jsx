/**
 * PipelineDiagram — the data journey as a source-by-source animation.
 * Pick a source; a single indicator travels Bronze → Silver → Gold → API →
 * Dashboard (most sources) or stops at Gold (ENTSO-E prices, which have no
 * live API route yet). Each arrival lights up the matching preview below.
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SOURCES, STAGES, CABLE_NOTES } from '../../data/pipelineSources.js'
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion.js'
import { PreviewPanel } from './PreviewPanel.jsx'

const DEFAULT_DWELL_MS = 1300

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

function StageNode({ stage, index, visited, current, source, onDashboardClick }) {
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

function Connector({ traveled, source, cableKey }) {
  const [open, setOpen] = useState(false)
  const note = cableKey && CABLE_NOTES[cableKey]
  const style = traveled ? { '--stage-color': source.color } : undefined

  return (
    <div className={'pipeline-connector' + (traveled ? ' pipeline-connector--traveled' : '')} style={style}>
      <span className="pipeline-connector__line" aria-hidden="true" />
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
  const reducedMotion = usePrefersReducedMotion()
  const navigate = useNavigate()
  const timeoutRef = useRef(null)

  const source = SOURCES.find(s => s.id === selectedId)

  useEffect(() => {
    if (reducedMotion) {
      setStageIndex(source.visitedCount - 1)
      return
    }
    let cancelled = false
    let i = 0
    const tick = () => {
      if (cancelled) return
      setStageIndex(i)
      if (i < source.visitedCount - 1) {
        const dwell = source.dwell?.[i] ?? DEFAULT_DWELL_MS
        timeoutRef.current = setTimeout(() => { i += 1; tick() }, dwell)
      }
    }
    tick()
    return () => { cancelled = true; clearTimeout(timeoutRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, reducedMotion])

  const currentKind = STAGES[stageIndex].kind

  return (
    <div className="pipeline-diagram">
      <div className="source-toggle-row" role="tablist" aria-label="Choisir une source">
        {SOURCES.map(s => (
          <SourceToggle key={s.id} source={s} active={s.id === selectedId} onSelect={setSelectedId} />
        ))}
      </div>
      {source.note && <p className="pipeline-diagram__source-note">{source.note}</p>}

      <div className="pipeline-diagram__track">
        <div className="data-lake-group">
          <span className="data-lake-group__label">Data lake — ADLS Gen2</span>
          <div className="data-lake-group__stages">
            <StageNode stage={STAGES[0]} index={0} visited={0 < source.visitedCount} current={stageIndex === 0} source={source} />
            <Connector traveled={stageIndex >= 1} source={source} cableKey="cleaning" />
            <StageNode stage={STAGES[1]} index={1} visited={1 < source.visitedCount} current={stageIndex === 1} source={source} />
          </div>
        </div>

        <Connector traveled={stageIndex >= 2} source={source} cableKey="aggregation" />
        <StageNode stage={STAGES[2]} index={2} visited={2 < source.visitedCount} current={stageIndex === 2} source={source} />
        <Connector traveled={stageIndex >= 3 && 3 < source.visitedCount} source={source} />
        <StageNode stage={STAGES[3]} index={3} visited={3 < source.visitedCount} current={stageIndex === 3} source={source} />
        <Connector traveled={stageIndex >= 4 && 4 < source.visitedCount} source={source} />
        <StageNode
          stage={STAGES[4]}
          index={4}
          visited={4 < source.visitedCount}
          current={stageIndex === 4}
          source={source}
          onDashboardClick={() => navigate('/')}
        />
      </div>

      <div className="preview-panel">
        <p className="preview-panel__stage-label">{STAGES[stageIndex].label}</p>
        <PreviewPanel source={source} stageKind={currentKind} />
      </div>
    </div>
  )
}
