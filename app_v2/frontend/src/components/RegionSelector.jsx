/**
 * RegionSelector — custom compact dropdown, not a native <select>.
 *
 * Needed because a native select always shows the selected <option>'s own
 * text as its closed-state label — there's no way to show a short code
 * ("HDF") closed while keeping the full name ("Hauts-de-France") in the
 * open list. Click-outside and Escape close it; arrow keys aren't wired
 * (small, single-purpose list — acceptable for now).
 */
import { useEffect, useRef, useState } from 'react'

// Standard INSEE/RTE region abbreviations — short enough to keep the closed
// field compact regardless of which region is picked.
const REGION_CODES = {
  'Auvergne-Rhône-Alpes': 'ARA',
  'Bourgogne-Franche-Comté': 'BFC',
  'Bretagne': 'BRE',
  'Centre-Val de Loire': 'CVL',
  'Corse': 'COR',
  'Grand Est': 'GES',
  'Hauts-de-France': 'HDF',
  'Île-de-France': 'IDF',
  'Normandie': 'NOR',
  'Nouvelle-Aquitaine': 'NAQ',
  'Occitanie': 'OCC',
  'Pays de la Loire': 'PDL',
  "Provence-Alpes-Côte d'Azur": 'PACA',
}

/** @param {{ regions: Array<{code_insee:string,region:string}>, selected: string, onChange: (code:string)=>void, loading?: boolean }} props */
export function RegionSelector({ regions, selected, onChange, loading = false }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  useEffect(() => {
    function onDocClick(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    function onKey(e) { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  const selectedRegion = regions.find(r => r.code_insee === selected)
  const closedLabel = selectedRegion ? (REGION_CODES[selectedRegion.region] || selectedRegion.region) : 'Toutes'

  function pick(code) {
    onChange(code)
    setOpen(false)
  }

  return (
    <div className="region-selector" data-testid="region-selector" ref={rootRef}>
      <span className="selector-label">Région</span>
      <button
        type="button"
        className="region-selector__button"
        onClick={() => setOpen(o => !o)}
        disabled={loading}
        aria-haspopup="listbox"
        aria-expanded={open}
        data-testid="region-select"
      >
        <span>{closedLabel}</span>
        <svg viewBox="0 0 16 16" width="11" height="11" fill="currentColor" aria-hidden="true">
          <path d="M7.247 11.14L2.451 5.658C1.885 5.013 2.345 4 3.204 4h9.592a1 1 0 0 1 .753 1.659l-4.796 5.48a1 1 0 0 1-1.506 0z" />
        </svg>
      </button>
      {open && (
        <ul className="region-selector__list" role="listbox" aria-label="Sélectionner une région">
          <li role="option" aria-selected={!selected}
            className={`region-selector__option${!selected ? ' region-selector__option--active' : ''}`}
            onClick={() => pick('')}>
            Toutes les régions
          </li>
          {regions.map(r => (
            <li key={r.code_insee} role="option" aria-selected={selected === r.code_insee}
              className={`region-selector__option${selected === r.code_insee ? ' region-selector__option--active' : ''}`}
              onClick={() => pick(r.code_insee)}>
              {r.region}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
