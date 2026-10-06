/**
 * PipelineDiagram — the data journey as a source-by-source animated flow.
 * Pick a source; a single indicator travels Bronze → Silver → Gold → API →
 * Dashboard (most sources) or stops at Gold (ENTSO-E prices, which have no
 * live API route yet). Each stage holds its colour once reached — it isn't
 * a progress bar, it's a trace of what this source's data just passed
 * through — and its preview sits right beside it, not in a separate panel.
 *
 * Bronze/Silver/Gold/API/Dashboard are grouped under the real Azure
 * services that host them (ADLS Gen2 / SQL Server / Function Apps / Static
 * Web Apps) — this reflects the certification-era (v1) architecture this
 * portfolio piece is built to explain, not the cost-trimmed v2 deployment
 * actually serving this page today (see `watt_watcher_unazureing` —
 * deliberate, not stale).
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { SOURCES, STAGES, CABLE_NOTES } from '../../data/pipelineSources.js'
import { usePrefersReducedMotion } from '../../hooks/usePrefersReducedMotion.js'
import { PreviewPanel } from './PreviewPanel.jsx'

const DEFAULT_DWELL_MS = 1300
const BEAD_TRAVEL_MS = 500

function StageIcon({ kind }) {
  switch (kind) {
    case 'bronze':
    case 'silver':
      return <img className="pipeline-stage__icon-img" src="/logos/azure/storage-container.svg" alt="" aria-hidden="true" />
    case 'gold':
      return <img className="pipeline-stage__icon-img" src="/logos/azure/sql-database.svg" alt="" aria-hidden="true" />
    case 'api':
      return <img className="pipeline-stage__icon-img" src="/logos/azure/function-apps.svg" alt="" aria-hidden="true" />
    case 'dashboard':
      return <img className="pipeline-stage__icon-img" src="/logos/azure/dashboard.svg" alt="" aria-hidden="true" />
    default:
      return null
  }
}

function ServiceCard({ icon, title, children }) {
  return (
    <div className="pipeline-service">
      <p className="pipeline-service__head">
        <img className="pipeline-service__icon" src={icon} alt="" aria-hidden="true" />
        <span className="pipeline-service__title">{title}</span>
      </p>
      <div className="pipeline-service__body">{children}</div>
    </div>
  )
}

function StageNode({ stage, inScope, passed, current, source, onDashboardClick }) {
  const isDashboard = stage.kind === 'dashboard'
  const style = passed ? { '--stage-color': source.color, '--stage-glow': source.glow } : undefined
  const preview = source.previews[stage.kind]

  const content = (
    <>
      <span className="pipeline-stage__glow" aria-hidden="true" />
      <span className="pipeline-stage__icon"><StageIcon kind={stage.kind} /></span>
      <span className="pipeline-stage__label">{stage.label}</span>
      <span className="pipeline-stage__sub">{stage.sub}</span>
    </>
  )

  const className = 'pipeline-stage'
    + (inScope ? '' : ' pipeline-stage--muted')
    + (passed ? ' pipeline-stage--passed' : '')
    + (current ? ' pipeline-stage--current' : '')
    + (isDashboard ? ' pipeline-stage--link' : '')

  const node = isDashboard
    ? <button type="button" className={className} style={style} onClick={onDashboardClick} title="Aller au dashboard">{content}</button>
    : <div className={className} style={style}>{content}</div>

  return (
    <div className="pipeline-stage-row">
      {node}
      {preview && (
        <div className="pipeline-stage-row__preview">
          <PreviewPanel source={source} stageKind={stage.kind} />
        </div>
      )}
    </div>
  )
}

function Connector({ traveled, source, cableKey, reducedMotion, inline }) {
  const [open, setOpen] = useState(false)
  const note = cableKey && CABLE_NOTES[cableKey]
  const style = traveled ? { '--stage-color': source.color } : undefined
  const beadRef = useRef(null)

  useEffect(() => {
    const bead = beadRef.current
    if (!bead) return
    bead.getAnimations().forEach(a => a.cancel())
    if (!traveled || reducedMotion) return
    bead.animate([
      { offset: 0, left: '0%', top: '0%', opacity: 0 },
      { offset: 0.15, left: '0%', top: '0%', opacity: 1 },
      { offset: 0.85, opacity: 1 },
      { offset: 1, left: '100%', top: '100%', opacity: 0 },
    ], { duration: BEAD_TRAVEL_MS, easing: 'linear' })
  }, [traveled, reducedMotion])

  return (
    <div
      className={'pipeline-connector' + (traveled ? ' pipeline-connector--traveled' : '') + (inline ? ' pipeline-connector--inline' : '')}
      style={style}
    >
      <span className="pipeline-connector__line" aria-hidden="true" />
      <i className="pipeline-connector__bead" ref={beadRef} aria-hidden="true" />
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
      {source.logo
        ? (
          <span className="source-toggle__logo-wrap" aria-hidden="true">
            <img className="source-toggle__logo source-toggle__logo--light" src={source.logo} alt="" />
            <img className="source-toggle__logo source-toggle__logo--dark" src={source.logoDark || source.logo} alt="" />
          </span>
        )
        : <span className="source-toggle__dot" aria-hidden="true" />}
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

  const stageProps = (index) => ({
    stage: STAGES[index],
    index,
    inScope: index < source.visitedCount,
    passed: index <= stageIndex,
    current: stageIndex === index,
    source,
  })

  return (
    <div className="pipeline-diagram">
      <div className="pipeline-diagram__body">
        <div className="source-toggle-col" role="tablist" aria-label="Choisir une source">
          {SOURCES.map(s => (
            <SourceToggle key={s.id} source={s} active={s.id === selectedId} onSelect={setSelectedId} />
          ))}
        </div>

        <div className="pipeline-diagram__main">
          {source.note && <p className="pipeline-diagram__source-note">{source.note}</p>}

          <div className="pipeline-diagram__track">
            <Connector key={source.id} traveled source={source} reducedMotion={reducedMotion} />

            <ServiceCard icon="/logos/azure/storage-accounts.svg" title="ADLS Gen 2">
              <StageNode {...stageProps(0)} />
              <Connector traveled={1 <= stageIndex} source={source} cableKey="cleaning" reducedMotion={reducedMotion} inline />
              <StageNode {...stageProps(1)} />
            </ServiceCard>

            <Connector traveled={2 <= stageIndex} source={source} cableKey="aggregation" reducedMotion={reducedMotion} />
            <ServiceCard icon="/logos/azure/sql-server.svg" title="SQL Server">
              <StageNode {...stageProps(2)} />
            </ServiceCard>

            <Connector traveled={3 <= stageIndex && 3 < source.visitedCount} source={source} reducedMotion={reducedMotion} />
            <ServiceCard icon="/logos/azure/function-apps.svg" title="Function Apps">
              <StageNode {...stageProps(3)} />
            </ServiceCard>

            <Connector traveled={4 <= stageIndex && 4 < source.visitedCount} source={source} reducedMotion={reducedMotion} />
            <ServiceCard icon="/logos/azure/static-web-apps.svg" title="Static Web Apps">
              <StageNode {...stageProps(4)} onDashboardClick={() => navigate('/')} />
            </ServiceCard>
          </div>
        </div>
      </div>
    </div>
  )
}
