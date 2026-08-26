/**
 * CarbonGauge tests — Story 5.1, Task 6.1
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CarbonGauge, computeCarbonIntensity } from '../CarbonGauge.jsx'

// ── computeCarbonIntensity unit tests ────────────────────────────────────────

describe('computeCarbonIntensity', () => {
  it('returns 0 for empty sources', () => {
    expect(computeCarbonIntensity({})).toBe(0)
  })

  it('returns 0 when all values are zero or negative', () => {
    expect(computeCarbonIntensity({ nucleaire: 0, eolien: -5 })).toBe(0)
  })

  it('computes weighted average for nuclear (12 gCO₂/kWh)', () => {
    // Pure nuclear → should return 12
    expect(computeCarbonIntensity({ nucleaire: 500 })).toBe(12)
  })

  it('computes weighted average for coal (820 gCO₂/kWh)', () => {
    expect(computeCarbonIntensity({ charbon: 1000 })).toBe(820)
  })

  it('computes correct weighted average for mix', () => {
    // 500 MW nuclear (12) + 500 MW gas (490) → (500*12 + 500*490) / 1000 = 251
    expect(computeCarbonIntensity({ nucleaire: 500, gaz: 500 })).toBe(251)
  })

  it('ignores unknown sources (factor = 0)', () => {
    // unknown source contributes totalMw but 0 CO2
    expect(computeCarbonIntensity({ nucleaire: 100, unknown_source: 100 })).toBe(6)
  })

  it('returns integer (rounds result)', () => {
    const result = computeCarbonIntensity({ nucleaire: 300, eolien: 100 })
    expect(Number.isInteger(result)).toBe(true)
  })
})

// ── CarbonGauge component tests ───────────────────────────────────────────────

describe('CarbonGauge', () => {
  it('renders the section with data-testid', () => {
    render(<CarbonGauge sources={{}} />)
    expect(screen.getByTestId('carbon-gauge')).toBeInTheDocument()
  })

  it('shows skeleton when loading', () => {
    render(<CarbonGauge sources={{}} loading />)
    expect(screen.getByTestId('carbon-gauge-skeleton')).toBeInTheDocument()
    expect(screen.queryByTestId('carbon-value')).toBeNull()
  })

  it('displays intensity value', () => {
    render(<CarbonGauge sources={{ nucleaire: 500 }} />)
    expect(screen.getByTestId('carbon-value')).toHaveTextContent('12')
  })

  it('displays zero for empty sources', () => {
    render(<CarbonGauge sources={{}} />)
    expect(screen.getByTestId('carbon-value')).toHaveTextContent('0')
  })

  it('displays unit label', () => {
    render(<CarbonGauge sources={{ gaz: 100 }} />)
    expect(screen.getByTestId('carbon-value')).toHaveTextContent('gCO₂/kWh')
  })
})
