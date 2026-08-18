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
 * Fetch list of available regions from production data.
 * Derives unique regions from a broad production query.
 *
 * @returns {Promise<Array<{code_insee: string, region: string}>>}
 */
export async function fetchRegions() {
  const result = await fetchProduction({ limit: 1000 })
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
 * Fetch grid maintenance events from fact_maintenance.
 * @param {Object} params
 * @param {string} [params.regionCode]
 * @param {number} [params.limit]
 * @returns {Promise<{data: Array, total_records: number}>}
 */
export async function fetchMaintenance({ regionCode, limit = 100 } = {}) {
  return apiGet('/v1/maintenance', { region_code: regionCode, limit })
}
