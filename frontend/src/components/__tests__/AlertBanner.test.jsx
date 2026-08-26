/**
 * AlertBanner tests — Story 5.2, Task 4.3
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AlertBanner } from '../AlertBanner.jsx'

const criticalAlert = {
  alert_id: 'abc-123',
  type: 'OVERPRODUCTION',
  severity: 'CRITICAL',
  region: '11',
  region_label: 'Île-de-France',
  details: 'Production dépasse la conso de 15%',
  timestamp: '2025-06-15T10:00:00+00:00',
  ratio: 1.15,
  acknowledged: false,
}

const warningAlert = {
  ...criticalAlert,
  alert_id: 'def-456',
  type: 'NEGATIVE_PRICE_RISK',
  severity: 'WARNING',
  details: 'Risque de prix négatif',
}

describe('AlertBanner', () => {
  it('renders nothing when alert is null', () => {
    const { container } = render(<AlertBanner alert={null} onDismiss={() => {}} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders alert details for CRITICAL severity', () => {
    render(<AlertBanner alert={criticalAlert} onDismiss={() => {}} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Île-de-France')).toBeInTheDocument()
    expect(screen.getByText('Production dépasse la conso de 15%')).toBeInTheDocument()
  })

  it('renders alert details for WARNING severity', () => {
    render(<AlertBanner alert={warningAlert} onDismiss={() => {}} />)
    expect(screen.getByText('Risque de prix négatif')).toBeInTheDocument()
  })

  it('calls onDismiss and disappears when dismiss button clicked', () => {
    const onDismiss = vi.fn()
    render(<AlertBanner alert={criticalAlert} onDismiss={onDismiss} />)
    const btn = screen.getByRole('button', { name: /fermer/i })
    fireEvent.click(btn)
    expect(onDismiss).toHaveBeenCalledOnce()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('has CRITICAL severity data attribute', () => {
    render(<AlertBanner alert={criticalAlert} onDismiss={() => {}} />)
    expect(screen.getByRole('alert')).toHaveAttribute('data-severity', 'CRITICAL')
  })

  it('has WARNING severity data attribute', () => {
    render(<AlertBanner alert={warningAlert} onDismiss={() => {}} />)
    expect(screen.getByRole('alert')).toHaveAttribute('data-severity', 'WARNING')
  })

  it('dismiss button has accessible label', () => {
    render(<AlertBanner alert={criticalAlert} onDismiss={() => {}} />)
    expect(screen.getByRole('button', { name: /fermer/i })).toBeInTheDocument()
  })

  it('falls back to region code when region_label is missing', () => {
    const alert = { ...criticalAlert, region_label: undefined }
    render(<AlertBanner alert={alert} onDismiss={() => {}} />)
    expect(screen.getByText('11')).toBeInTheDocument()
  })
})
