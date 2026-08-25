/**
 * PipelinePage — the data journey as a clickable flow: each step reveals
 * what actually happens there (sources, cloud infra, cleaning, DB schema,
 * API routes). Clicking "Dashboard" jumps to the dashboard tab.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PipelineFlow } from '../components/PipelineFlow.jsx'
import { JsonBlock } from '../components/JsonBlock.jsx'

const STEPS = [
  { id: 'collecte',  title: 'Collecte',        sub: 'toutes les 15 min' },
  { id: 'cloud',     title: 'Architecture cloud', sub: 'Azure' },
  { id: 'nettoyage', title: 'Nettoyage',       sub: 'médaillon' },
  { id: 'base',      title: 'Base de données', sub: 'PostgreSQL' },
  { id: 'api',       title: 'API',             sub: 'REST' },
  { id: 'dashboard', title: 'Dashboard',       sub: 'voir en direct →' },
]

const SOURCES = [
  {
    name: 'RTE eCO2mix',
    desc: 'Production et consommation électrique par région, filière par filière.',
    tag: 'API REST',
  },
  {
    name: 'Open-Meteo',
    desc: 'Température, vent, couverture nuageuse — pour mettre la production en regard de la météo.',
    tag: 'API REST',
  },
  {
    name: 'Maintenance réseau',
    desc: 'Événements de maintenance planifiée par région.',
    tag: 'API REST',
  },
]

const SAMPLE_RECORD = {
  code_insee_region: '53',
  libelle_region: 'Bretagne',
  date_heure: '2026-08-25T14:15:00+00:00',
  consommation: 3120,
  eolien: 842,
  solaire: 156,
  nucleaire: 0,
  hydraulique: 61,
  pompage: '0',
  bioenergies: 34,
  column_68: null,
}

function CollectePanel() {
  return (
    <>
      <p>
        Toutes les 15 minutes, le pipeline interroge trois sources publiques et
        rapatrie tout ce qu'elles ont de nouveau :
      </p>
      <div className="content-grid">
        {SOURCES.map(s => (
          <div key={s.name} className="content-grid__item">
            <p className="content-grid__title">{s.name}</p>
            <p className="content-grid__desc">{s.desc}</p>
            <span className="content-grid__tag">{s.tag}</span>
          </div>
        ))}
      </div>
      <p style={{ marginTop: 16 }}>
        Voici, sans aucune retouche, ce que l'API RTE renvoie pour une région et un
        horodatage donnés. Tout ne survit pas au nettoyage — les lignes barrées
        ci-dessous sont écartées avant d'atteindre la base :
      </p>
      <JsonBlock data={SAMPLE_RECORD} dropKeys={['libelle_region', 'column_68']} />
      <p className="content-caption">
        <code>column_68</code> est une colonne fantôme, toujours vide, qui traîne dans
        toutes les réponses de l'API — supprimée. <code>libelle_region</code> est
        redondante : le nom de la région se retrouve par jointure sur{' '}
        <code>code_insee_region</code>, pas besoin de le stocker deux fois. Les champs
        qui restent glissent presque tels quels dans la base :{' '}
        <code>eolien</code> → <code>eolien_mw</code>,{' '}
        <code>consommation</code> → <code>consommation_mw</code>,{' '}
        <code>code_insee_region</code> → clé étrangère <code>id_region</code>.
      </p>
    </>
  )
}

function CloudPanel() {
  return (
    <>
      <p>
        Cette étape tourne entièrement sur Microsoft Azure. Des tâches planifiées
        (Azure Functions) se réveillent toutes les 15 minutes, appellent les 3 sources,
        et déposent le résultat tel quel sur un espace de stockage cloud (Azure Data
        Lake Storage Gen2) — organisé par source et par date, sans aucune
        transformation à ce stade. L'idée : garder une trace fidèle de ce que chaque
        source a réellement renvoyé, pour pouvoir toujours revenir en arrière si un
        nettoyage se révèle plus tard imparfait.
      </p>
      <table className="content-table">
        <tbody>
          <tr><td>Compute</td><td>Azure Functions — déclenchement planifié, facturé à l'exécution</td></tr>
          <tr><td>Stockage brut</td><td>Azure Data Lake Storage Gen2 — un dossier par source et par date</td></tr>
        </tbody>
      </table>
      <p className="content-caption">
        Rien ne tourne en continu : le calcul ne coûte (et ne consomme) que le temps
        réel d'exécution, quelques secondes toutes les 15 minutes.
      </p>
    </>
  )
}

function NettoyagePanel() {
  return (
    <>
      <p>
        C'est ici que la donnée brute devient exploitable, en suivant un pattern
        classique en ingénierie de données : l'architecture médaillon.
      </p>
      <div className="medallion-strip">
        <span className="medallion-chip medallion-chip--bronze">Bronze — brut</span>
        <span className="pipeline-arrow" aria-hidden="true"><span className="pipeline-arrow__dot" /></span>
        <span className="medallion-chip medallion-chip--silver">Argent — nettoyé</span>
        <span className="pipeline-arrow" aria-hidden="true"><span className="pipeline-arrow__dot" /></span>
        <span className="medallion-chip medallion-chip--gold">Or — structuré</span>
      </div>
      <p>
        Le brut (bronze) est renommé, retypé, dédoublonné, puis passé à l'étage
        suivant (argent). Le point le plus délicat n'est pas technique : que faire
        d'une valeur manquante dépend de ce qu'elle veut dire. Un <code>null</code> sur
        une puissance ne signifie pas « production nulle » mais « pas encore
        publiée » (RTE publie avec un léger retard) — l'écraser à zéro raconterait
        une fausse histoire, donc la ligne est plutôt marquée que modifiée.
      </p>
    </>
  )
}

function BasePanel() {
  return (
    <>
      <p>
        La donnée nettoyée termine dans une base PostgreSQL (Supabase), organisée en
        modèle en étoile : une table de faits — une mesure par région, horodatage et
        filière — entourée de trois tables de référence. C'est la dernière étape (or)
        de l'architecture médaillon, prête à être interrogée directement.
      </p>
      <div className="content-diagram">
        <img
          src="/diagrams/db-schema-dark.svg"
          alt="Schéma de la base : la table de faits fact_energy_flow référence dim_region, dim_time et dim_source via des clés étrangères sur id_region, id_date et id_source."
        />
      </div>
    </>
  )
}

function ApiPanel() {
  const routes = [
    ['/v1/production/regional', 'production par région et filière'],
    ['/v1/meteo/regional', 'météo par région'],
    ['/v1/capacity/regional', 'capacités installées'],
    ['/v1/maintenance', 'alertes de maintenance'],
    ['/v1/export/csv', 'export CSV filtré par date/région'],
    ['/health', 'état du service'],
  ]
  return (
    <>
      <p>
        Une API REST publique, en lecture seule et sans authentification (les données
        ne sont pas sensibles), expose cette base au dashboard — et à qui veut
        l'interroger directement.
      </p>
      <table className="content-table">
        <tbody>
          {routes.map(([path, desc]) => (
            <tr key={path}>
              <td><span className="method-badge">GET</span> <code>{path}</code></td>
              <td>{desc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

const PANELS = {
  collecte: CollectePanel,
  cloud: CloudPanel,
  nettoyage: NettoyagePanel,
  base: BasePanel,
  api: ApiPanel,
}

export default function PipelinePage() {
  const [selected, setSelected] = useState('collecte')
  const navigate = useNavigate()

  const handleSelect = (id) => {
    if (id === 'dashboard') {
      navigate('/')
      return
    }
    setSelected(id)
  }

  const Panel = PANELS[selected]

  return (
    <main id="main-content" className="app-main content-page">
      <section className="glass-card content-card">
        <p className="content-kicker">Pipeline de données</p>
        <p>
          Trois sources publiques, un nettoyage automatisé, une base prête à
          l'emploi. Clique sur une étape pour voir ce qui s'y passe :
        </p>

        <PipelineFlow steps={STEPS} selected={selected} onSelect={handleSelect} />

        <div className="pipeline-panel">
          <Panel />
        </div>
      </section>
    </main>
  )
}
