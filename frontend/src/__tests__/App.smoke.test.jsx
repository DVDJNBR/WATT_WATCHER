/**
 * App smoke test — Story 5.1, Task 6.3
 *
 * E2E smoke test: dashboard renders, fetches data, shows correct structure.
 * Mocks API services to avoid real HTTP and Azure AD dependency.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App.jsx'
import { fetchProduction, fetchRegions, fetchAlerts } from '../services/api.js'

// vi.mock hoisted above imports — factory must NOT reference module-level vars
vi.mock('../services/api.js', () => ({
  fetchProduction: vi.fn(),
  fetchRegions:    vi.fn(),
  fetchAlerts:     vi.fn(),
}))

vi.mock('../services/auth.js', () => ({
  acquireToken:        vi.fn().mockResolvedValue('mock-token'),
  getMsalInstance:     vi.fn(),
  getCurrentAccount:   vi.fn().mockResolvedValue(null),
}))

// FranceMap uses react-simple-maps which fetches a GeoJSON URL —
// not possible in jsdom. Render a lightweight stub instead.
vi.mock('../components/FranceMap.jsx', () => ({
  FranceMap: ({ regions, selectedCode, onSelect }) => (
    <div data-testid="france-map">
      {regions.map(r => (
        <button key={r.code_insee} onClick={() => onSelect(r.code_insee)}>
          {r.region}
        </button>
      ))}
      {selectedCode && <span data-testid="map-selected">{selectedCode}</span>}
    </div>
  ),
}))

const MOCK_DATA = [
  {
    code_insee: '11',
    region: 'Île-de-France',
    timestamp: '2024-01-15T10:00:00Z',
    sources: { nucleaire: 450, eolien: 120, solaire: 30 },
    facteur_charge: 0.85,
  },
  {
    code_insee: '11',
    region: 'Île-de-France',
    timestamp: '2024-01-15T10:30:00Z',
    sources: { nucleaire: 460, eolien: 115, solaire: 25 },
    facteur_charge: 0.86,
  },
]

const MOCK_REGIONS = [
  { code_insee: '11', region: 'Île-de-France' },
  { code_insee: '84', region: 'Auvergne-Rhône-Alpes' },
]

describe('App smoke test (Task 6.3)', () => {
  beforeEach(() => {
    document.documentElement.setAttribute('data-theme', 'dark')
    vi.clearAllMocks()
    fetchProduction.mockResolvedValue({ data: MOCK_DATA, total_records: 2, request_id: 'smoke-1' })
    fetchRegions.mockResolvedValue(MOCK_REGIONS)
    fetchAlerts.mockResolvedValue({ alerts: [] })
  })

  it('renders the dashboard layout container', () => {
    render(<App />)
    expect(screen.getByTestId('app-layout')).toBeInTheDocument()
  })

  it('renders WATT WATCHER branding in header', () => {
    render(<App />)
    expect(screen.getByText(/WATT WATCHER/)).toBeInTheDocument()
  })

  it('renders france map for region selection', () => {
    render(<App />)
    expect(screen.getByTestId('france-map')).toBeInTheDocument()
  })

  it('renders theme toggle button', () => {
    render(<App />)
    expect(screen.getByTestId('theme-toggle')).toBeInTheDocument()
  })

  it('renders 4 KPI cards', () => {
    render(<App />)
    expect(screen.getAllByTestId('kpi-card')).toHaveLength(4)
  })

  it('shows last-updated timestamp after data loads (AC #1)', async () => {
    render(<App />)
    await waitFor(() => {
      expect(screen.getByTestId('last-updated')).toBeInTheDocument()
    })
  })

  it('calls fetchProduction on mount (AC #1 — real-time data)', async () => {
    render(<App />)
    await waitFor(() => {
      expect(fetchProduction).toHaveBeenCalled()
    })
  })

  it('calls fetchRegions on mount for map population', async () => {
    render(<App />)
    await waitFor(() => {
      expect(fetchRegions).toHaveBeenCalled()
    })
  })

  it('theme toggle switches between dark and light (AC #3)', async () => {
    const user = userEvent.setup()
    render(<App />)
    const toggle = screen.getByTestId('theme-toggle')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    await user.click(toggle)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    await user.click(toggle)
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })
})
