/**
 * RenewableShare — part EnR (énergies renouvelables) badge + sparkline.
 *
 * Renewable = éolien + solaire + hydraulique + bioénergies, matching
 * dim_source.is_green in the Gold schema. Nuclear is deliberately excluded
 * (low-carbon but not renewable — RTE keeps these two concepts distinct;
 * "part EnR" is the standard French term for this specific ratio).
 */
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'

const RENEWABLE_SOURCES = new Set(['eolien', 'solaire', 'hydraulique', 'bioenergies'])

export function computeRenewableShare(sources = {}) {
  let total = 0, renewable = 0
  for (const [src, mw] of Object.entries(sources)) {
    if (typeof mw !== 'number' || mw <= 0) continue
    total += mw
    if (RENEWABLE_SOURCES.has(src)) renewable += mw
  }
  return total > 0 ? Math.round((renewable / total) * 1000) / 10 : 0
}

function shareColor(pct) {
  if (pct >= 40) return '#10b981'
  if (pct >= 20) return '#84cc16'
  return '#f59e0b'
}

/** @param {{ share: number, sparkData: Array<{t:string, v:number}>, loading?: boolean }} props */
export function RenewableShare({ share = 0, sparkData = [], loading = false }) {
  const color = shareColor(share)
  return (
    <div className="glass-card carbon-badge-card" data-testid="renewable-share">
      {loading ? (
        <div className="skeleton" style={{ height: 88 }} />
      ) : (
        <>
          <p className="carbon-badge__label" title="Part de la production actuelle venant d'énergies renouvelables (éolien, solaire, hydraulique, bioénergies) — le nucléaire, bas carbone mais pas renouvelable, n'est pas compté ici.">Part EnR (énergies renouvelables)</p>
          <div className="carbon-badge__row">
            <span className="carbon-badge__number" style={{ color }}>{share}</span>
            <span className="carbon-badge__unit">%</span>
          </div>
          {sparkData.length > 1 && (
            <ResponsiveContainer width="100%" height={36}>
              <LineChart data={sparkData} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                <Line type="monotone" dataKey="v" stroke={color} dot={false} strokeWidth={1.5} isAnimationActive={false} />
                <Tooltip
                  formatter={v => [`${v} %`, 'Part EnR']}
                  labelFormatter={l => l}
                  contentStyle={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)', fontSize: 11, borderRadius: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </>
      )}
    </div>
  )
}
