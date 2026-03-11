/**
 * API client — Story 5.1, Task 3.1
 *
 * Fetches production data from GET /v1/production/regional.
 * AC #1: Real-time data fetch with auth headers.
 * AC #3: Graceful error handling with typed errors.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'
const API_KEY  = import.meta.env.VITE_API_KEY || ''

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
 * Perform an authenticated GET request.
 * @param {string} path  e.g. '/v1/production/regional'
 * @param {Record<string,any>} params  query parameters
 * @returns {Promise<any>}
 */
async function authGet(path, params = {}) {
  const qs = buildQueryString(params)
  const url = `${API_BASE}${path}${qs}`

  const headers = {
    'Content-Type': 'application/json',
    'X-Api-Key': API_KEY,
  }

  const response = await fetch(url, { headers })

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
 * AC #1: Populates production charts.
 * AC #2: Filterable by region_code.
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
  return authGet('/v1/production/regional', {
    region_code:  regionCode,
    start_date:   startDate,
    end_date:     endDate,
    source_type:  sourceType,
    limit,
    offset,
  })
}

/**
 * Fetch active alerts — Story 5.2, Task 3.3.
 *
 * AC #1: Polls /v1/alerts every 60 s to keep dashboard current.
 *
 * @param {Object} params
 * @param {string} [params.regionCode]  filter by region
 * @param {string} [params.status]      'active' | 'acknowledged' | undefined (all)
 * @param {number} [params.days]        look-back window (default 7)
 * @param {number} [params.limit]       max alerts (default 50)
 * @returns {Promise<{alerts: Array, total: number}>}
 */
export async function fetchAlerts({ regionCode, status = 'active', days = 7, limit = 50 } = {}) {
  return authGet('/v1/alerts', { region_code: regionCode, status, days, limit })
}

/**
 * Trigger the full ETL pipeline: Bronze → Silver → Gold SQL.
 * Returns when the pipeline completes (may take ~60 s if SQL was paused).
 *
 * @returns {Promise<{status: string, stages: object}>}
 */
export async function triggerPipeline() {
  const url = `${API_BASE}/v1/pipeline/refresh`
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Api-Key': API_KEY },
  })
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
