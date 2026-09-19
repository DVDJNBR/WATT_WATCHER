/**
 * MixRatioGauge — current mix split renouvelable / nucléaire / fossile, as a
 * half-donut ratio instead of a trend-over-time line (replaces RenewableShare
 * + RenewableTrendChart). Sits next to CarbonBadge in the Renouvelable tab's
 * KPI row — it's the "why" behind the CO₂ number: intensity follows directly
 * from how much of the mix is fossile vs. low-carbon (nucléaire) vs.
 * renouvelable. Legend sits beside the arc (not stacked under it) so each
 * label reads next to its slice instead of as a separate block below.
 */
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { categorize, CATEGORY_ORDER, CATEGORY_COLORS, CATEGORY_LABELS } from '../utils/mixCategories.js'

/** @param {{ sources: Object, loading?: boolean }} props */
export function MixRatioGauge({ sources = {}, loading = false }) {
  const byCategory = categorize(sources)
  const total = CATEGORY_ORDER.reduce((s, k) => s + byCategory[k], 0)
  const data = CATEGORY_ORDER.map(key => ({
    key,
    name: CATEGORY_LABELS[key],
    value: byCategory[key],
    pct: total > 0 ? Math.round((byCategory[key] / total) * 1000) / 10 : 0,
  }))

  return (
    <div className="glass-card carbon-badge-card mix-ratio-gauge" data-testid="mix-ratio-gauge">
      {loading ? (
        <div className="skeleton" style={{ height: 88 }} />
      ) : (
        <>
          <p
            className="carbon-badge__label"
            title="Répartition de la production actuelle en 3 grandes familles : renouvelable, nucléaire (bas carbone mais pas renouvelable), fossile. C'est ce ratio qui détermine l'intensité CO₂ ci-contre."
          >
            Répartition du mix
          </p>
          {total === 0 ? (
            <p className="mix-ratio-gauge__empty">Aucune donnée</p>
          ) : (
            <div className="mix-ratio-gauge__body">
              <div className="mix-ratio-gauge__arc">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                    <Pie
                      data={data}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="100%"
                      startAngle={180}
                      endAngle={0}
                      innerRadius="55%"
                      outerRadius="100%"
                      stroke="none"
                      isAnimationActive={false}
                    >
                      {data.map(d => <Cell key={d.key} fill={CATEGORY_COLORS[d.key]} />)}
                    </Pie>
                    <Tooltip
                      formatter={(v, n, entry) => [`${entry.payload.pct} %`, entry.payload.name]}
                      contentStyle={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)', fontSize: 11, borderRadius: 6 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <ul className="mix-ratio-gauge__legend">
                {data.map(d => (
                  <li key={d.key} className="mix-ratio-gauge__legend-item">
                    <span className="mix-ratio-gauge__dot" style={{ background: CATEGORY_COLORS[d.key] }} />
                    <span className="mix-ratio-gauge__legend-label">{d.name}</span>
                    <strong>{d.pct}%</strong>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  )
}
