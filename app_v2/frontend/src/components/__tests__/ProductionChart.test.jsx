/**
 * ProductionChart tests — Story 5.1, Task 6.1
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ProductionChart, transformProductionData } from '../ProductionChart.jsx'

const MOCK_RECORDS = [
  {
    timestamp: '2024-01-01T10:00:00Z',
    sources: { nucleaire: 450, eolien: 120, solaire: 30 },
  },
  {
    timestamp: '2024-01-01T10:30:00Z',
    sources: { nucleaire: 460, eolien: 110, solaire: 35 },
  },
]

// ── transformProductionData unit tests ───────────────────────────────────────

describe('transformProductionData', () => {
  it('returns an array of the same length', () => {
    const result = transformProductionData(MOCK_RECORDS)
    expect(result).toHaveLength(2)
  })

  it('adds formatted timestamp field', () => {
    const result = transformProductionData(MOCK_RECORDS)
    expect(result[0]).toHaveProperty('timestamp')
    expect(typeof result[0].timestamp).toBe('string')
  })

  it('spreads source values into the row', () => {
    const result = transformProductionData(MOCK_RECORDS)
    expect(result[0].nucleaire).toBe(450)
    expect(result[0].eolien).toBe(120)
    expect(result[0].solaire).toBe(30)
  })

  it('handles empty array', () => {
    expect(transformProductionData([])).toEqual([])
  })
})

// ── ProductionChart component tests ──────────────────────────────────────────

describe('ProductionChart', () => {
  it('shows loading skeleton when loading', () => {
    render(<ProductionChart data={[]} loading />)
    expect(screen.getByTestId('production-chart-loading')).toBeInTheDocument()
  })

  it('shows error state when error is provided', () => {
    render(<ProductionChart data={[]} error="timeout" />)
    expect(screen.getByTestId('production-chart-error')).toBeInTheDocument()
    expect(screen.getByText(/timeout/i)).toBeInTheDocument()
  })

  it('renders chart section with data', () => {
    render(<ProductionChart data={MOCK_RECORDS} />)
    expect(screen.getByTestId('production-chart')).toBeInTheDocument()
  })

  it('renders chart title', () => {
    render(<ProductionChart data={MOCK_RECORDS} />)
    expect(screen.getByText('Production par source (MW)')).toBeInTheDocument()
  })

  it('shows empty state when data is empty', () => {
    render(<ProductionChart data={[]} />)
    expect(screen.getByTestId('production-chart-empty')).toBeInTheDocument()
    expect(screen.getByText(/Aucune donnée disponible/i)).toBeInTheDocument()
  })
})
