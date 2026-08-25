/**
 * PipelineFlow — clickable row of pipeline steps. Each step is a real button
 * (keyboard/screen-reader accessible), connected by arrow separators.
 * Selecting a step is purely presentational — the parent decides what to show.
 */
export function PipelineFlow({ steps, selected, onSelect }) {
  return (
    <div className="pipeline-flow" role="tablist" aria-label="Étapes du pipeline">
      {steps.map((step, i) => (
        <div key={step.id} className="pipeline-flow__item">
          <button
            type="button"
            role="tab"
            aria-selected={selected === step.id}
            className={'pipeline-step' + (selected === step.id ? ' pipeline-step--active' : '')}
            onClick={() => onSelect(step.id)}
          >
            <span className="pipeline-step__index">{i + 1}</span>
            <span className="pipeline-step__title">{step.title}</span>
            <span className="pipeline-step__sub">{step.sub}</span>
          </button>
          {i < steps.length - 1 && (
            <span className="pipeline-arrow" aria-hidden="true">
              <span className="pipeline-arrow__dot" />
            </span>
          )}
        </div>
      ))}
    </div>
  )
}
