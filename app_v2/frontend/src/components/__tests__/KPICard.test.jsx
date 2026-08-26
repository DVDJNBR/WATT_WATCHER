/**
 * KPICard tests — Story 5.1, Task 6.1
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { KPICard } from '../KPICard.jsx'

describe('KPICard', () => {
  it('renders title and value', () => {
    render(<KPICard title="Production" value={1234} />)
    expect(screen.getByText('Production')).toBeInTheDocument()
    expect(screen.getByTestId('kpi-value')).toHaveTextContent('1234')
  })

  it('renders unit when provided', () => {
    render(<KPICard title="Intensité" value={42} unit="gCO₂/kWh" />)
    expect(screen.getByTestId('kpi-value')).toHaveTextContent('gCO₂/kWh')
  })

  it('does not render unit when omitted', () => {
    render(<KPICard title="Source" value="Nucléaire" />)
    const val = screen.getByTestId('kpi-value')
    expect(val.querySelector('.kpi-unit')).toBeNull()
  })

  it('shows skeleton when loading', () => {
    render(<KPICard title="Loading" value={0} loading />)
    expect(screen.getByTestId('kpi-skeleton')).toBeInTheDocument()
    expect(screen.queryByTestId('kpi-value')).toBeNull()
  })

  it('shows trend up badge', () => {
    render(<KPICard title="KPI" value={99} trend="up" />)
    expect(screen.getByText('↑')).toBeInTheDocument()
  })

  it('shows trend down badge', () => {
    render(<KPICard title="KPI" value={99} trend="down" />)
    expect(screen.getByText('↓')).toBeInTheDocument()
  })

  it('shows flat trend badge', () => {
    render(<KPICard title="KPI" value={99} trend="flat" />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders no badge when trend is undefined', () => {
    render(<KPICard title="KPI" value={99} />)
    expect(screen.queryByText('↑')).toBeNull()
    expect(screen.queryByText('↓')).toBeNull()
  })
})
