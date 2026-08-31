/**
 * PipelinePage — the data journey as an animated, per-source diagram
 * (PipelineDiagram), plus the supplementary detail that doesn't fit inside
 * it: cloud infra, the full DB schema, the satellite fact tables, the
 * threshold calibration, and the full API route list.
 */
import { PipelineDiagram } from '../components/pipeline/PipelineDiagram.jsx'

const SATELLITE_FACTS = [
  ['fact_meteo', 'région × horodatage', 'Open-Meteo — température, vent, nébulosité'],
  ['fact_capacity', 'région × filière × année', 'RTE — puissance installée de référence'],
  ['fact_maintenance', '1 ligne / événement', "RTE — arrêts et maintenances planifiés"],
  ['fact_market_price', 'horodatage seul', 'ENTSO-E — prix day-ahead, France entière'],
]

const THRESHOLD_CALIBRATION = [
  ['5 %', '90.4 %', '4.1 %', '85.7 %'],
  ['10 %', '80.0 %', '4.1 %', '75.9 %'],
  ['15 %', '63.3 %', '4.5 %', '65.4 %'],
  ['20 %', '46.1 %', '5.0 %', '53.6 %'],
  ['30 %', '17.3 %', '7.4 %', '29.5 %'],
  ['40 % (actuel)', '5.4 %', '10.4 %', '13.1 %'],
  ['50 %', '2.0 %', '5.4 %', '2.5 %'],
]

const API_ROUTES = [
  ['/v1/production/regional', 'production par région et filière'],
  ['/v1/meteo/regional', 'météo par région'],
  ['/v1/capacity/regional', 'capacités installées'],
  ['/v1/maintenance', 'alertes de maintenance'],
  ['/v1/curtailment/regional', 'part du surplus éolien+solaire par région lors des prix négatifs'],
  ['/v1/export/csv', 'export CSV filtré par date/région'],
  ['/health', 'état du service'],
]

export default function PipelinePage() {
  return (
    <main id="main-content" className="app-main">
      <section className="glass-card content-card pipeline-section">
        <p className="content-kicker">Pipeline de données</p>
        <p>
          Cinq sources publiques, un nettoyage automatisé, une base prête à
          l'emploi. Choisis une source pour suivre son chemin :
        </p>

        <PipelineDiagram />
      </section>

      <div className="content-page">
      <section className="glass-card content-card">
        <p className="content-heading" style={{ marginTop: 0 }}>Architecture cloud</p>
        <p>
          La collecte tourne entièrement sur Microsoft Azure. Des tâches planifiées
          (Azure Functions) se réveillent toutes les 15 minutes, appellent chaque
          source, et déposent le résultat tel quel sur un espace de stockage cloud
          (Azure Data Lake Storage Gen2) avant toute transformation.
        </p>
        <table className="content-table">
          <tbody>
            <tr><td>Compute</td><td>Azure Functions — déclenchement planifié, facturé à l'exécution</td></tr>
            <tr><td>Stockage brut/nettoyé</td><td>Azure Data Lake Storage Gen2 — conteneurs bronze/silver, un dossier par source et par date</td></tr>
            <tr><td>Base de données</td><td>PostgreSQL (Supabase) — la couche Gold</td></tr>
          </tbody>
        </table>
        <p className="content-caption">
          Rien ne tourne en continu : le calcul ne coûte (et ne consomme) que le temps
          réel d'exécution, quelques secondes toutes les 15 minutes.
        </p>
      </section>

      <section className="glass-card content-card">
        <p className="content-heading" style={{ marginTop: 0 }}>Base de données</p>
        <p>
          La donnée nettoyée termine dans une base PostgreSQL (Supabase), organisée en
          modèle en étoile : une table de faits centrale — une mesure par région,
          horodatage et filière — entourée de trois tables de référence.
        </p>
        <div className="content-diagram">
          <img
            src="/diagrams/db-schema-dark.svg"
            alt="Schéma de la base : la table de faits fact_energy_flow référence dim_region, dim_time et dim_source via des clés étrangères sur id_region, id_date et id_source."
          />
        </div>
        <p className="content-caption">
          Ce schéma est le cœur du modèle. Quatre autres tables de faits se sont
          greffées dessus au fil du projet, chacune simple — une mesure de plus
          accrochée aux mêmes dimensions (<code>dim_region</code>,{' '}
          <code>dim_time</code>) plutôt qu'un nouveau schéma :
        </p>
        <table className="content-table">
          <tbody>
            {SATELLITE_FACTS.map(([name, grain, desc]) => (
              <tr key={name}>
                <td><code>{name}</code></td>
                <td>{grain}</td>
                <td>{desc}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <p style={{ marginTop: 24 }}>
          <code>fact_market_price</code> mérite un mot à part : c'est la seule table
          qui ne référence jamais <code>dim_region</code>. La France est une zone de
          marché day-ahead unique sur ENTSO-E — il n'existe tout simplement pas de
          prix par région à stocker. C'est cette table qui a servi à calibrer
          honnêtement le seuil « excédent export » affiché sur le dashboard : en
          croisant, créneau par créneau de 15 min (mars-août 2026, ~65 jours de
          données RTE réelles), le ratio national éolien+solaire/consommation
          (nucléaire exclu — il ne module pas, l'inclure ne fait que refléter son
          export structurel permanent) avec les vrais prix négatifs du marché.
        </p>
        <table className="content-table content-table--stats">
          <thead>
            <tr>
              <th>Seuil</th>
              <th>Créneaux déclenchés</th>
              <th>Précision</th>
              <th>Rappel</th>
            </tr>
          </thead>
          <tbody>
            {THRESHOLD_CALIBRATION.map(([seuil, declenches, precision, rappel]) => (
              <tr key={seuil} className={seuil.includes('actuel') ? 'is-current' : undefined}>
                <td>{seuil}</td>
                <td>{declenches}</td>
                <td>{precision}</td>
                <td>{rappel}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="content-caption">
          Précision = part des créneaux où le seuil est dépassé qui coïncident vraiment
          avec un prix négatif. Rappel = part des créneaux à prix négatif effectivement
          détectés par le seuil. 40 % reste le meilleur compromis testé (précision la
          plus haute, 10 %), mais aucun seuil ne rend ce signal fiable au sens strict :
          c'est un indicateur bruité, pas un détecteur — la vraie décision d'arrêt se
          prend poste par poste, à une échelle que les données publiques ne permettent
          pas de voir.
        </p>
      </section>

      <section className="glass-card content-card">
        <p className="content-heading" style={{ marginTop: 0 }}>Routes API</p>
        <p>
          Une API REST publique, en lecture seule et sans authentification (les données
          ne sont pas sensibles), expose cette base au dashboard — et à qui veut
          l'interroger directement.
        </p>
        <table className="content-table">
          <tbody>
            {API_ROUTES.map(([path, desc]) => (
              <tr key={path}>
                <td><span className="method-badge">GET</span> <code>{path}</code></td>
                <td>{desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      </div>
    </main>
  )
}
