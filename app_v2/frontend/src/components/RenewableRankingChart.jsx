/**
 * RenewableRankingChart — part renouvelable actuelle, une barre par région,
 * triée du meilleur au moins bon élève. Remplace l'ancien graphique
 * "Renouvelable vs nucléaire vs fossile dans le temps" : cette page parle
 * maintenant de comparaison régionale (voir aussi la carte en mode
 * "Renouvelable"), pas d'évolution temporelle — ce chart et la carte
 * partagent le même calcul (utils/mixCategories) pour rester cohérents.
 */
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer, LabelList } from 'recharts'
import { useMemo } from 'react'
import { CATEGORY_COLORS } from '../utils/mixCategories.js'

/** @param {{ data: Array<{code_insee:string, region:string, pct:number}>, loading?: boolean }} props */
export function RenewableRankingChart({ data = [], loading = false }) {
  const chartData = useMemo(
    () => [...data].sort((a, b) => b.pct - a.pct),
    [data]
  )

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="renewable-ranking-loading">
        <h2 className="chart-title">Part renouvelable par région</h2>
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </section>
    )
  }

  if (!chartData.length) {
    return (
      <section className="glass-card chart-card" data-testid="renewable-ranking-empty">
        <h2 className="chart-title">Part renouvelable par région</h2>
        <div className="empty-state"><p className="empty-state__title">Aucune donnée disponible</p></div>
      </section>
    )
  }

  return (
    <section className="glass-card chart-card" data-testid="renewable-ranking">
      <h2
        className="chart-title"
        title="Part de la production actuelle de chaque région venant d'énergies renouvelables (éolien, solaire, hydraulique, bioénergies), triée du meilleur au moins bon élève."
      >
        Part renouvelable par région
      </h2>
      <div style={{ flex: '1 1 0', minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 28, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.15} horizontal={false} />
            <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }} />
            <YAxis type="category" dataKey="region" width={110} tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }} />
            <Tooltip
              formatter={v => [`${v} %`, 'Part renouvelable']}
              contentStyle={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)', borderRadius: 8, fontSize: '0.8rem' }}
              labelStyle={{ color: 'var(--color-text)', fontWeight: 600 }}
            />
            <Bar dataKey="pct" radius={[0, 4, 4, 0]} isAnimationActive={false} maxBarSize={18}>
              {chartData.map(d => <Cell key={d.code_insee} fill={CATEGORY_COLORS.renouvelable} fillOpacity={0.85} />)}
              <LabelList dataKey="pct" position="right" formatter={v => `${v}%`} fill="var(--color-text-muted)" fontSize={10} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
