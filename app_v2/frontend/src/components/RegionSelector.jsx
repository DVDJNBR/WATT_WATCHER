/**
 * RegionSelector — Story 5.1, Task 2.4
 *
 * Dropdown to select a French region; triggers chart refresh on change.
 * AC #2: Region selection updates all charts.
 */

/** @param {{ regions: Array<{code_insee:string,region:string}>, selected: string, onChange: (code:string)=>void, loading?: boolean }} props */
export function RegionSelector({ regions, selected, onChange, loading = false }) {
  return (
    <div className="region-selector" data-testid="region-selector">
      <label htmlFor="region-select" className="selector-label">
        Région
      </label>

      <select
        id="region-select"
        value={selected}
        onChange={e => onChange(e.target.value)}
        disabled={loading}
        className="selector-input"
        data-testid="region-select"
        aria-label="Sélectionner une région"
      >
        <option value="">Toutes les régions</option>
        {regions.map(r => (
          <option key={r.code_insee} value={r.code_insee}>
            {r.region}
          </option>
        ))}
      </select>
    </div>
  )
}
