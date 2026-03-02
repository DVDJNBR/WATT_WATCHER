/**
 * AlertHistory tests — Story 5.2, Task 4.3
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AlertHistory } from '../AlertHistory.jsx'

const sampleAlerts = [
  {
    alert_id: 'a1',
    type: 'OVERPRODUCTION',
    severity: 'CRITICAL',
    region: '11',
    region_label: 'Île-de-France',
    details: 'Surproduction critique',
    timestamp: '2025-06-15T10:00:00+00:00',
  },
  {
    alert_id: 'a2',
    type: 'NEGATIVE_PRICE_RISK',
    severity: 'WARNING',
    region: '84',
    region_label: 'Auvergne-Rhône-Alpes',
    details: 'Risque prix négatif',
    timestamp: '2025-06-15T03:00:00+00:00',
  },
]

describe('AlertHistory', () => {
  it('shows empty message when no alerts', () => {
    render(<AlertHistory alerts={[]} />)
    expect(screen.getByText(/aucune alerte/i)).toBeInTheDocument()
  })

  it('shows loading message when loading=true', () => {
    render(<AlertHistory alerts={[]} loading={true} />)
    expect(screen.getByText(/chargement/i)).toBeInTheDocument()
  })

  it('renders alert list with correct count', () => {
    render(<AlertHistory alerts={sampleAlerts} />)
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('renders region labels', () => {
    render(<AlertHistory alerts={sampleAlerts} />)
    expect(screen.getByText('Île-de-France')).toBeInTheDocument()
    expect(screen.getByText('Auvergne-Rhône-Alpes')).toBeInTheDocument()
  })

  it('renders alert details text', () => {
    render(<AlertHistory alerts={sampleAlerts} />)
    expect(screen.getByText('Surproduction critique')).toBeInTheDocument()
    expect(screen.getByText('Risque prix négatif')).toBeInTheDocument()
  })

  it('renders severity badges', () => {
    render(<AlertHistory alerts={sampleAlerts} />)
    expect(screen.getByText('CRITIQUE')).toBeInTheDocument()
    expect(screen.getByText('ATTENTION')).toBeInTheDocument()
  })

  it('renders a list element per alert', () => {
    render(<AlertHistory alerts={sampleAlerts} />)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
  })

  it('renders timestamps as <time> elements', () => {
    render(<AlertHistory alerts={sampleAlerts} />)
    const times = document.querySelectorAll('time')
    expect(times.length).toBe(2)
  })
})
