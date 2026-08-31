/**
 * CurtailmentShareChart — which regions actually drove negative-price events,
 * ranked as horizontal bars instead of a choropleth.
 *
 * Replaces an earlier map version: a % share read from a hover-only tooltip
 * on a colored region wasn't legible ("42% of what?") without interacting
 * first. A ranked list makes the comparison and the value self-explanatory
 * at a glance — no hover required.
 *
 * Each bar is this region's share of the NATIONAL wind+solar surplus (over
 * its own consumption), summed across every 15-min slot where the national
 * price went negative. Deliberately renewable-only — nuclear-heavy regions
 * structurally export several times their own consumption at all times, so
 * including nuclear would just re-surface that permanent export pattern
 * instead of the actual, curtailable oversupply RTE throttles. There is no
 * per-region negative price in France (single EPEX bidding zone) — this
 * chart answers "which region's renewable output pushed the *national*
 * price negative", not "what was the price here".
 */
import { memo } from 'react'

/**
 * @param {{
 *   data: Array<{code_insee:string, region:string, share_pct:number, surplus_mwh_15min:number, n_slots:number}>,
 *   loading?: boolean,
 * }} props
 */
export const CurtailmentShareChart = memo(function CurtailmentShareChart({
  data = [],
  loading = false,
}) {
  const rows = [...data].sort((a, b) => b.share_pct - a.share_pct)
  const maxShare = Math.max(1, ...rows.map(r => r.share_pct))

  return (
    <section className="glass-card content-card" data-testid="curtailment-share-chart">
      <p className="content-kicker">Contribution au surplus renouvelable</p>
      <p>
        Part du surplus éolien + solaire national (production régionale moins
        consommation régionale, nucléaire exclu) cumulée sur tous les créneaux
        de 15 min où le prix de marché national est passé négatif.
      </p>

      {loading ? (
        <div className="skeleton" style={{ height: 320, marginTop: 16 }} />
      ) : (
        <div className="curtailment-bars">
          {rows.map(r => (
            <div className="curtailment-bar-row" key={r.code_insee}>
              <span className="curtailment-bar-row__label">{r.region}</span>
              <div className="curtailment-bar-row__track">
                <div
                  className="curtailment-bar-row__fill"
                  style={{ width: `${Math.max(0, (r.share_pct / maxShare) * 100)}%` }}
                />
              </div>
              <span className="curtailment-bar-row__value">{r.share_pct.toFixed(1)}%</span>
              <span className="curtailment-bar-row__detail">
                {Math.round(r.surplus_mwh_15min).toLocaleString('fr-FR')} MW cumulés · {r.n_slots} créneaux
              </span>
            </div>
          ))}
        </div>
      )}

      <p className="content-caption">
        France est une zone de marché unique — il n'existe pas de prix par région.
        Ce classement répond à une autre question : quelle région a le plus contribué
        au surplus qui a fait chuter le prix national, pas quel a été le prix ici.
      </p>
    </section>
  )
})
