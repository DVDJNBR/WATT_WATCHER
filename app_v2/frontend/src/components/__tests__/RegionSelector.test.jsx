/**
 * RegionSelector tests — Story 5.1, Task 6.1
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RegionSelector } from '../RegionSelector.jsx'

const REGIONS = [
  { code_insee: '11', region: 'Île-de-France' },
  { code_insee: '84', region: 'Auvergne-Rhône-Alpes' },
]

describe('RegionSelector', () => {
  it('renders label and select', () => {
    render(<RegionSelector regions={[]} selected="" onChange={() => {}} />)
    expect(screen.getByTestId('region-selector')).toBeInTheDocument()
    expect(screen.getByTestId('region-select')).toBeInTheDocument()
    expect(screen.getByText('Région')).toBeInTheDocument()
  })

  it('renders "Toutes les régions" default option', () => {
    render(<RegionSelector regions={[]} selected="" onChange={() => {}} />)
    expect(screen.getByText('Toutes les régions')).toBeInTheDocument()
  })

  it('renders all region options', () => {
    render(<RegionSelector regions={REGIONS} selected="" onChange={() => {}} />)
    expect(screen.getByText('Île-de-France')).toBeInTheDocument()
    expect(screen.getByText('Auvergne-Rhône-Alpes')).toBeInTheDocument()
  })

  it('calls onChange when user selects a region', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<RegionSelector regions={REGIONS} selected="" onChange={onChange} />)
    await user.selectOptions(screen.getByTestId('region-select'), '11')
    expect(onChange).toHaveBeenCalledWith('11')
  })

  it('disables select when loading', () => {
    render(<RegionSelector regions={REGIONS} selected="" onChange={() => {}} loading />)
    expect(screen.getByTestId('region-select')).toBeDisabled()
  })

  it('reflects the selected value', () => {
    render(<RegionSelector regions={REGIONS} selected="84" onChange={() => {}} />)
    expect(screen.getByTestId('region-select')).toHaveValue('84')
  })
})
