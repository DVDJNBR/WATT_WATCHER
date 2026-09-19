/**
 * Shared renouvelable/nucléaire/fossile categorization — same 3-family
 * regrouping used by the map's "Renouvelable" mode, the mix ratio gauge,
 * and the per-region ranking chart on the Renouvelable tab, so all three
 * views agree on the same numbers.
 */
const RENEWABLE = new Set(['eolien', 'solaire', 'hydraulique', 'bioenergies'])
const FOSSIL = new Set(['thermique', 'gaz', 'charbon', 'fioul'])

export const CATEGORY_ORDER = ['nucleaire', 'renouvelable', 'fossile']
export const CATEGORY_COLORS = { renouvelable: '#10b981', nucleaire: '#7c3aed', fossile: '#ef4444' }
export const CATEGORY_LABELS = { renouvelable: 'Renouvelable', nucleaire: 'Nucléaire', fossile: 'Fossile' }

export function categorize(sources) {
  let renouvelable = 0, nucleaire = 0, fossile = 0
  for (const [src, mw] of Object.entries(sources || {})) {
    if (typeof mw !== 'number' || mw <= 0) continue
    if (RENEWABLE.has(src)) renouvelable += mw
    else if (src === 'nucleaire') nucleaire += mw
    else if (FOSSIL.has(src)) fossile += mw
  }
  return { renouvelable, nucleaire, fossile }
}

/** Renewable share (%) of a source breakdown — 0-100, rounded to 0.1. */
export function renewablePct(sources) {
  const { renouvelable, nucleaire, fossile } = categorize(sources)
  const total = renouvelable + nucleaire + fossile
  return total > 0 ? Math.round((renouvelable / total) * 1000) / 10 : 0
}
