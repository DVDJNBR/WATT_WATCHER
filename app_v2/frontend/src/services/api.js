/**
 * API client — fetches dataviz data from the FastAPI backend.
 *
 * Public, read-only endpoints — no auth (portfolio showroom).
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

export class ApiError extends Error {
  constructor(message, status, requestId) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.requestId = requestId
  }
}

/**
 * Build query string from a params object (omit null/undefined values).
 * @param {Record<string,string|number|null|undefined>} params
 * @returns {string}
 */
export function buildQueryString(params) {
  const entries = Object.entries(params).filter(([, v]) => v != null && v !== '')
  if (!entries.length) return ''
  return '?' + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString()
}

/**
 * Perform a GET request against the API.
 * @param {string} path  e.g. '/v1/production/regional'
 * @param {Record<string,any>} params  query parameters
 * @returns {Promise<any>}
 */
async function apiGet(path, params = {}) {
  const qs = buildQueryString(params)
  const url = `${API_BASE}${path}${qs}`

  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' } })

  if (!response.ok) {
    let errorBody = {}
    try { errorBody = await response.json() } catch (_) { /* ignore */ }
    throw new ApiError(
      errorBody.message || `HTTP ${response.status}`,
      response.status,
      errorBody.request_id,
    )
  }

  return response.json()
}

/**
 * Fetch regional production data.
 *
 * @param {Object} params
 * @param {string} [params.regionCode]  INSEE code
 * @param {string} [params.startDate]   ISO 8601
 * @param {string} [params.endDate]     ISO 8601
 * @param {string} [params.sourceType]  energy source filter
 * @param {number} [params.limit]       default 100
 * @param {number} [params.offset]      default 0
 * @returns {Promise<{data: Array, total_records: number, request_id: string}>}
 */
export async function fetchProduction({ regionCode, startDate, endDate, sourceType, limit = 100, offset = 0 } = {}) {
  return apiGet('/v1/production/regional', {
    region_code:  regionCode,
    start_date:   startDate,
    end_date:     endDate,
    source_type:  sourceType,
    limit,
    offset,
  })
}

/**
 * Fetch every record of a paginated endpoint.
 *
 * query_production() (the only caller today) fetches and aggregates the
 * *entire* requested date range internally in one DB query no matter what
 * `limit` is passed — pagination only slices that already-computed result
 * afterward. Chunking the fetch into 1000-row pages therefore used to mean
 * ~9 sequential HTTP round-trips for a week of data, each one redoing that
 * same full-range aggregation from scratch for nothing (confirmed: this
 * was the dominant cost in the dashboard's ~20-25s cold load, well above
 * the backend's actual per-query time). One request with a big enough
 * limit does the same backend work exactly once.
 *
 * @param {(params: Object) => Promise<{data: Array, total_records: number}>} fetchFn
 * @param {Object} params
 * @param {number} pageSize  Unused for the common single-shot path; only
 *   sizes the fallback pages below (kept as a parameter so callers can tune
 *   it, e.g. for endpoints with a smaller server-side limit cap).
 * @returns {Promise<{data: Array, total_records: number}>}
 */
async function fetchAllPages(fetchFn, params, pageSize) {
  // Covers the widest range exposed in the UI (30 days x 12 regions x 96
  // slots/day ≈ 34.5k aggregated records) in one request — matches the
  // server-side cap in api/models.py.
  const SINGLE_SHOT_LIMIT = 50000
  // Safety net, not a real constraint, for the fallback path below.
  const MAX_PAGES = 45

  const first = await fetchFn({ ...params, limit: SINGLE_SHOT_LIMIT, offset: 0 })
  const firstData = first.data || []
  const total = first.total_records ?? firstData.length

  if (firstData.length >= total) {
    return { data: firstData, total_records: total }
  }

  // Only reached for a range wider than SINGLE_SHOT_LIMIT can cover in one
  // shot — not reachable via the UI's own controls, but a manually-typed
  // date range could exceed it. Page the remainder the old way.
  const totalPages = Math.min(Math.ceil(total / pageSize), MAX_PAGES)
  const rest = await Promise.all(
    Array.from({ length: Math.max(totalPages - 1, 0) }, (_, i) => {
      const offset = firstData.length + i * pageSize
      return fetchFn({ ...params, limit: pageSize, offset }).then(r => r.data || [])
    })
  )

  return { data: firstData.concat(...rest), total_records: total }
}

/**
 * Fetch ALL regional production records for the given range (paginated).
 * @param {Object} params  same shape as fetchProduction, minus limit/offset
 * @returns {Promise<{data: Array, total_records: number}>}
 */
export async function fetchAllProduction(params = {}) {
  return fetchAllPages(fetchProduction, params, 1000)
}

/**
 * Fetch list of available regions from production data.
 * Derives unique regions from a recent production query — bounded to the
 * last 30 days on purpose. An unbounded query has no WHERE clause to filter
 * on, so the backend falls back to sorting up to 700k rows with no index to
 * lean on; harmless while fact_energy_flow was small, but it now hangs
 * outright since the history backfill grew that table ~6x. All 12 regions
 * report every 15 minutes, so even 2 days is generous margin for a brief
 * regional outage — narrower than that just makes query_production's
 * internal full-range aggregation (see fetchAllPages) needlessly expensive
 * for a call that only needs "which regions exist right now."
 *
 * @returns {Promise<Array<{code_insee: string, region: string}>>}
 */
export async function fetchRegions() {
  const end = new Date()
  const start = new Date(end)
  start.setDate(start.getDate() - 2)
  const iso = d => d.toISOString().slice(0, 10)
  const result = await fetchProduction({ limit: 1000, startDate: iso(start), endDate: iso(end) })
  const seen = new Map()
  for (const record of result.data) {
    if (!seen.has(record.code_insee)) {
      seen.set(record.code_insee, { code_insee: record.code_insee, region: record.region })
    }
  }
  return Array.from(seen.values()).sort((a, b) => a.region.localeCompare(b.region))
}

/**
 * Fetch météo data (temperature + wind) from fact_meteo.
 * @param {Object} params
 * @param {string} [params.regionCode]
 * @param {string} [params.startDate]
 * @param {string} [params.endDate]
 * @param {number} [params.limit]
 * @returns {Promise<{data: Array, total_records: number}>}
 */
export async function fetchMeteo({ regionCode, startDate, endDate, limit = 500 } = {}) {
  return apiGet('/v1/meteo/regional', {
    region_code: regionCode,
    start_date:  startDate,
    end_date:    endDate,
    limit,
  })
}

/**
 * Fetch installed capacity per region+source from fact_capacity.
 * @param {Object} params
 * @param {string} [params.regionCode]
 * @param {number} [params.annee]
 * @returns {Promise<{data: Array, total_records: number}>}
 */
export async function fetchCapacity({ regionCode, annee } = {}) {
  return apiGet('/v1/capacity/regional', { region_code: regionCode, annee })
}

/**
 * Fetch the national gaz/charbon/fioul fossil-thermal split from
 * fact_national_mix. France-wide only — RTE never publishes this per
 * region, only the combined "thermique" figure does (see production data).
 * @param {Object} params
 * @param {string} [params.startDate]
 * @param {string} [params.endDate]
 * @param {number} [params.limit]
 * @returns {Promise<{data: Array, total_records: number}>}
 */
export async function fetchNationalMix({ startDate, endDate, limit = 200 } = {}) {
  return apiGet('/v1/production/national-mix', {
    start_date: startDate,
    end_date:   endDate,
    limit,
  })
}

/**
 * Fetch grid maintenance events from fact_maintenance.
 * @param {Object} params
 * @param {string} [params.regionCode]
 * @param {number} [params.limit]
 * @returns {Promise<{data: Array, total_records: number}>}
 */
export async function fetchMaintenance({ regionCode, limit = 100 } = {}) {
  return apiGet('/v1/maintenance', { region_code: regionCode, limit })
}

/**
 * Fetch day-by-day negative-price slot counts + headline stats (total hours, record day).
 * @returns {Promise<{days: Array, stats: Object}>}
 */
export async function fetchCurtailmentCalendar() {
  return apiGet('/v1/curtailment/calendar')
}

/**
 * Fetch net cross-border physical flow (France <-> GB/CH/IT/ES) from
 * fact_cross_border_flow. Positive flow_mw = France exporting.
 * @param {Object} params
 * @param {string} [params.startDate]
 * @param {string} [params.endDate]
 * @returns {Promise<{data: Array, summary: Array, total_records: number}>}
 */
export async function fetchCrossBorder({ startDate, endDate } = {}) {
  return apiGet('/v1/export/cross-border', { start_date: startDate, end_date: endDate })
}

/**
 * Fetch large production unit locations (nuclear plants, wind farms, dams...)
 * for the map's source pictograms.
 * @param {Object} params
 * @param {string} [params.region]  full région name (e.g. "Bretagne"), not an INSEE code
 * @returns {Promise<{data: Array, total_records: number}>}
 */
export async function fetchProductionUnits({ region } = {}) {
  return apiGet('/v1/production/units', { region })
}
