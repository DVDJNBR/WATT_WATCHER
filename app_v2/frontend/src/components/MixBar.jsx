/**
 * MixBar — thin stacked bar showing the current production mix
 * repartition, with a plain wrapped legend below (same pattern as every
 * other chart's legend in this app — HistoryChart, MeteoChart, etc.).
 *
 * When `nationalDetail` (gaz/charbon/fioul, France-wide only — see
 * fetchNationalMix) is available, it replaces the single regional
 * "thermique" bucket with the finer split. Only valid for the France-wide
 * view: RTE never publishes that split per region. Every source with a
 * real value shows in the legend, however small — that detail is the
 * whole point of the national split.
 */
import { useMemo } from 'react'

const SOURCE_LABELS = {
  nucleaire:   'Nucléaire',
  eolien:      'Éolien',
  solaire:     'Solaire',
  hydraulique: 'Hydraulique',
  bioenergies: 'Bioénergies',
  thermique:   'Thermique fossile',
  gaz:         'Gaz',
  fioul:       'Fioul',
  charbon:     'Charbon',
}

const SOURCE_COLORS = {
  nucleaire:   '#7c3aed',
  eolien:      '#10b981',
  solaire:     '#f59e0b',
  hydraulique: '#3b82f6',
  bioenergies: '#84cc16',
  // Gaz gets its own red — the dominant fossil source, worth flagging on
  // sight. Charbon/fioul/thermique stay black/gray rather than adding yet
  // more hues for what's usually a sliver.
  gaz:         '#ef4444',
  thermique:   '#111827',
  charbon:     '#1f2937',
  fioul:       '#374151',
}

/**
 * 26.6% for anything sizable, more decimals the smaller it gets — down to
 * real precision, not a "basically nothing" placeholder. Whether charbon
 * is exactly 0% or a genuine 0.0001% is itself the interesting fact (the
 * latter means France briefly fired up a coal plant — worth seeing, not
 * hiding behind a generic "< 0.05%").
 */
function formatPct(pct) {
  if (pct === 0) return '0%'
  if (pct >= 1) return `${pct.toFixed(1)}%`
  if (pct >= 0.01) return `${pct.toFixed(2)}%`
  if (pct >= 0.0001) return `${pct.toFixed(4)}%`
  return '< 0,0001%'
}

/** @param {{ sources: Object, nationalDetail?: Object|null, loading?: boolean }} props */
export function MixBar({ sources = {}, nationalDetail = null, loading = false }) {
  const { entries, total } = useMemo(() => {
    const merged = { ...sources }
    if (nationalDetail) {
      // Always prefer the national split when we have it — the regional
      // "thermique" bucket can read 0 for a given instant even while gaz/
      // fioul are genuinely flowing nationally (rounding, slightly
      // different publish timing between the two feeds); gating this on
      // merged.thermique being present silently dropped gaz/fioul/charbon
      // any time that happened.
      delete merged.thermique
      for (const [src, mw] of Object.entries(nationalDetail)) {
        if (mw > 0) merged[src] = mw
      }
      // Charbon sitting at 0 is itself the interesting fact (France's coal
      // plants idle) — show it even then, unlike other sources which just
      // disappear when absent.
      if (merged.charbon == null) merged.charbon = nationalDetail.charbon ?? 0
    }
    const filtered = Object.entries(merged).filter(([src, v]) => v > 0 || src === 'charbon')
    const total = filtered.reduce((s, [, v]) => s + v, 0)
    const sorted = [...filtered].sort(([, a], [, b]) => b - a)
    return { entries: sorted, total }
  }, [sources, nationalDetail])

  return (
    <article className="glass-card mix-bar-card" data-testid="mix-bar">
      <span className="kpi-title" title="Répartition de la production actuelle par filière (nucléaire, EnR, thermique fossile).">
        Répartition du mix
      </span>

      {loading ? (
        <div className="skeleton" style={{ height: '3.5rem', marginTop: 8 }} />
      ) : !entries.length ? (
        <p className="kpi-value" style={{ fontSize: '1rem', color: 'var(--color-text-muted)' }}>—</p>
      ) : (
        <>
          <div className="mix-bar__track">
            {entries.map(([src, mw]) => (
              <div
                key={src}
                className="mix-bar__seg"
                style={{ flexBasis: `${(mw / total) * 100}%`, background: SOURCE_COLORS[src] || '#888' }}
                title={`${SOURCE_LABELS[src] || src} — ${Math.round(mw).toLocaleString('fr-FR')} MW (${formatPct((mw / total) * 100)})`}
              />
            ))}
          </div>
          <div className="mix-bar__legend">
            {entries.map(([src, mw]) => (
              <span key={src} className="mix-bar__legend-item">
                <span className="mix-bar__legend-dot" style={{ background: SOURCE_COLORS[src] || '#888' }} />
                {SOURCE_LABELS[src] || src} {formatPct((mw / total) * 100)}
              </span>
            ))}
          </div>
        </>
      )}
    </article>
  )
}
