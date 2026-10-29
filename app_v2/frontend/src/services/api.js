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
 * query_production() (the only caller today) paginates in SQL, so each page
 * costs the server only its own rows. Pages are capped server-side
 * (api/models.py, 10000) to bound the API container's memory, and fetched
 * at most PAGE_CONCURRENCY at a time for the same reason: a 3-month range
 * is ~11 pages, and firing them all at once would hold them all at once.
 *
 * @param {(params: Object) => Promise<{data: Array, total_records: number}>} fetchFn
 * @param {Object} params
 * @param {number} pageSize  must not exceed the endpoint's server-side cap
 * @returns {Promise<{data: Array, total_records: number}>}
 */
async function fetchAllPages(fetchFn, params, pageSize) {
  // Safety net, not a real constraint: 45 x 10000 covers well over a year.
  const MAX_PAGES = 45
  const PAGE_CONCURRENCY = 3

  // A week (12 regions x 96 slots/day x 7 ≈ 8k records) fits in this one.
  const first = await fetchFn({ ...params, limit: pageSize, offset: 0 })
  const firstData = first.data || []
  const total = first.total_records ?? firstData.length

  if (firstData.length >= total) {
    return { data: firstData, total_records: total }
  }

  const totalPages = Math.min(Math.ceil(total / pageSize), MAX_PAGES)
  const offsets = Array.from({ length: totalPages - 1 }, (_, i) => (i + 1) * pageSize)
  const pages = new Array(offsets.length)
  let next = 0
  const worker = async () => {
    while (next < offsets.length) {
      const i = next++
      const r = await fetchFn({ ...params, limit: pageSize, offset: offsets[i] })
      pages[i] = r.data || []
    }
  }
  await Promise.all(Array.from({ length: Math.min(PAGE_CONCURRENCY, offsets.length) }, worker))

  return { data: firstData.concat(...pages), total_records: total }
}

/**
 * Fetch ALL regional production records for the given range (paginated).
 * @param {Object} params  same shape as fetchProduction, minus limit/offset
 * @returns {Promise<{data: Array, total_records: number}>}
 */
export async function fetchAllProduction(params = {}) {
  // Matches the server-side cap (MAX_PRODUCTION_LIMIT in api/models.py).
  return fetchAllPages(fetchProduction, params, 10000)
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
 * Fetch per-region share of national wind+solar surplus during negative-price
 * windows — which regions actually drive curtailment, not just who produces
 * the most (nuclear/hydro deliberately excluded, see api/curtailment_service.py).
 * Whole-history by default, same reasoning as fetchCurtailmentCalendar: events
 * are sparse, a short date range would starve most regions of any data.
 * @returns {Promise<{data: Array, national_surplus_mwh_15min: number}>}
 */
export async function fetchCurtailmentRisk() {
  return apiGet('/v1/curtailment/regional')
}

/**
 * Fetch day-ahead spot price (EUR/MWh) over time — national, single-zone,
 * no region filter (matches how ENTSO-E publishes it).
 * @param {Object} params
 * @param {string} [params.startDate]
 * @param {string} [params.endDate]
 * @param {number} [params.limit]
 * @returns {Promise<{data: Array, total_records: number}>}
 */
export async function fetchMarketPrice({ startDate, endDate, limit = 20000 } = {}) {
  return apiGet('/v1/prices/regional', { start_date: startDate, end_date: endDate, limit })
}

/**
 * Fetch the most recent priced day, slot by slot: day-ahead price alongside
 * national consumption and wind+solar output, so the Prix tab can plot the
 * price against the residual load that sets it.
 * @returns {Promise<{day: string|null, data: Array, total_records: number}>}
 */
export async function fetchDayAhead() {
  return apiGet('/v1/prices/day-ahead')
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

/**
 * Latest timestamp available per fact table, plus `common_max` — the newest
 * instant every plotted series has data for. The dashboard anchors its window
 * on `common_max` rather than the wall clock, so all charts stop together
 * instead of trailing an empty axis where the slower feeds haven't landed.
 *
 * @returns {Promise<{data: {per_table: Record<string, string|null>, common_max: string|null}}>}
 */
export async function fetchDataRange() {
  return apiGet('/v1/data-range', {})
}
