/**
 * pipelineSources — describes what the animated Pipeline diagram shows for
 * each real data source. Every source visits Bronze → Silver → Gold; most
 * continue to API → Dashboard. ENTSO-E prices stop at Gold — there is no
 * live API route for fact_market_price yet (see docs/data_model.md).
 *
 * `visitedCount` is how many of the 5 fixed stages (bronze/silver/gold/
 * api/dashboard) this source's animated path covers, always starting at
 * bronze — no source skips a stage in the middle.
 */

export const STAGES = [
  { kind: 'bronze',    label: 'Bronze' },
  { kind: 'silver',    label: 'Silver' },
  { kind: 'gold',      label: 'Gold' },
  { kind: 'api',       label: 'Endpoints' },
  { kind: 'dashboard', label: 'Dashboard' },
]

export const SOURCES = [
  {
    id: 'rte-production',
    label: 'RTE eCO2mix',
    homepage: 'https://www.rte-france.com/eco2mix',
    lede: [
      { text: 'Toutes les 15 minutes, le ' }, { text: 'JSON', cls: 'tech' }, { text: " brut de l'" }, { text: 'API', cls: 'tech' },
      { text: ' RTE eCO2mix, concernant la ' }, { text: 'production', cls: 'data' }, { text: ', la ' }, { text: 'consommation', cls: 'data' },
      { text: ' et le ' }, { text: 'mix énergétique', cls: 'data' }, { text: ' régional, est stocké tel quel dans le ' }, { text: 'Data Lake', cls: 'storage' },
      { text: ', où il est nettoyé. Il est ensuite agrégé en ' }, { text: 'schéma en étoile', cls: 'tech' }, { text: ' dans la ' }, { text: 'base de données', cls: 'storage' },
      { text: ", puis exposé par l'" }, { text: 'API', cls: 'tech' }, { text: ' et affiché sur la ' }, { text: 'carte des centrales', cls: 'data' },
      { text: " et l'" }, { text: 'historique de consommation', cls: 'data' }, { text: ' du tableau de bord.' },
    ],
    logo: '/logos/rte.png',
    color: 'var(--color-source-rte)',
    glow: 'var(--color-source-rte-glow)',
    visitedCount: 5,
    dwell: [1300, 1300, 1500, 1100],
    previews: {
      bronze: {
        kind: 'json',
        path: 'bronze/rte/production/2026/08/28/eco2mix_regional_....json',
        data: {
          code_insee_region: '53',
          libelle_region: 'Bretagne',
          date_heure: '2026-08-28T14:15:00+02:00',
          consommation: 3120,
          eolien: 842,
          solaire: 156,
          nucleaire: 0,
          hydraulique: 61,
          pompage: '0',
          bioenergies: 34,
        },
      },
      silver: {
        kind: 'table',
        path: 'silver/rte/production/year=2026/month=08/day=28/data.parquet',
        columns: ['code_insee_region', 'date_heure', 'consommation_mw', 'eolien_mw', 'solaire_mw'],
        row: ['53', '2026-08-28T14:15:00Z', 3120, 842, 156],
      },
      gold: {
        kind: 'star',
        fact: {
          table: 'fact_energy_flow',
          columns: ['id_date', 'id_region', 'id_source', 'valeur_mw', 'consommation_mw'],
          row: [4821, 8, 2, 842, 3120],
        },
        dims: [
          { table: 'dim_time', columns: ['id_date', 'horodatage', 'heure'], row: [4821, '2026-08-28T12:15:00Z', 14] },
          { table: 'dim_region', columns: ['id_region', 'code_insee', 'nom_region'], row: [8, '53', 'Bretagne'] },
          { table: 'dim_source', columns: ['id_source', 'source_name', 'is_green'], row: [2, 'eolien', 1] },
        ],
      },
      api: { kind: 'api', route: 'GET /v1/production/regional?region_code=53' },
    },
  },
  {
    id: 'open-meteo',
    label: 'Open-Meteo',
    homepage: 'https://open-meteo.com',
    lede: [
      { text: 'Toutes les 15 minutes, le ' }, { text: 'JSON', cls: 'tech' }, { text: " brut de l'" }, { text: 'API', cls: 'tech' },
      { text: ' Open-Meteo, concernant la ' }, { text: 'température', cls: 'data' }, { text: ', le ' }, { text: 'vent', cls: 'data' },
      { text: ' et la ' }, { text: 'nébulosité', cls: 'data' }, { text: ' par région, est stocké tel quel dans le ' }, { text: 'Data Lake', cls: 'storage' },
      { text: ', où il est nettoyé. Il est ensuite agrégé en ' }, { text: 'schéma en étoile', cls: 'tech' }, { text: ' dans la ' }, { text: 'base de données', cls: 'storage' },
      { text: ", puis exposé par l'" }, { text: 'API', cls: 'tech' }, { text: ' et affiché sur la ' }, { text: 'carte de France', cls: 'data' },
      { text: ' et le ' }, { text: 'graphique météo régional', cls: 'data' }, { text: ' du tableau de bord.' },
    ],
    logo: '/logos/open-meteo.png',
    color: 'var(--color-source-meteo)',
    glow: 'var(--color-source-meteo-glow)',
    visitedCount: 5,
    dwell: [1300, 1300, 1500, 1100],
    previews: {
      bronze: {
        kind: 'json',
        path: 'bronze/meteo/regional/2026/08/28/eco2mix_regional_....json',
        data: {
          region_code: '53',
          region_name: 'Bretagne',
          timestamp: '2026-08-28T14:00',
          temperature_c: 19.4,
          wind_speed_10m: 24.8,
          cloudcover_pct: 62,
        },
      },
      silver: {
        kind: 'table',
        path: 'silver/meteo/regional/year=2026/month=08/data.parquet',
        columns: ['region_code', 'timestamp', 'temperature_c', 'wind_speed_10m', 'cloudcover_pct'],
        row: ['53', '2026-08-28T14:00', 19.4, 24.8, 62],
      },
      gold: {
        kind: 'star',
        fact: {
          table: 'fact_meteo',
          columns: ['id_date', 'id_region', 'temperature_c', 'wind_speed_10m', 'cloudcover_pct'],
          row: [4821, 8, 19.4, 24.8, 62],
        },
        dims: [
          { table: 'dim_time', columns: ['id_date', 'horodatage', 'heure'], row: [4821, '2026-08-28T12:00:00Z', 14] },
          { table: 'dim_region', columns: ['id_region', 'code_insee', 'nom_region'], row: [8, '53', 'Bretagne'] },
        ],
      },
      api: { kind: 'api', route: 'GET /v1/meteo/regional?region_code=53' },
    },
  },
  {
    id: 'odre-capacity',
    label: 'ODRÉ — Capacité installée',
    homepage: 'https://odre.opendatasoft.com',
    lede: [
      { text: 'Quotidiennement, le ' }, { text: 'CSV', cls: 'tech' }, { text: " brut de l'" }, { text: 'API', cls: 'tech' },
      { text: ' ODRÉ, concernant la ' }, { text: 'capacité installée', cls: 'data' }, { text: ' par ' }, { text: 'région', cls: 'data' },
      { text: ' et par ' }, { text: 'filière', cls: 'data' }, { text: ', est stocké tel quel dans le ' }, { text: 'Data Lake', cls: 'storage' },
      { text: ', où il est nettoyé. Il est ensuite agrégé en ' }, { text: 'schéma en étoile', cls: 'tech' }, { text: ' dans la ' }, { text: 'base de données', cls: 'storage' },
      { text: ", puis exposé par l'" }, { text: 'API', cls: 'tech' }, { text: ' et affiché sur le ' }, { text: 'graphique de production', cls: 'data' },
      { text: ' des différentes sources du tableau de bord.' },
    ],
    logo: '/logos/odre.svg',
    logoDark: '/logos/odre-dark.svg',
    color: 'var(--color-source-capacity)',
    glow: 'var(--color-source-capacity-glow)',
    visitedCount: 5,
    dwell: [1300, 1300, 1500, 1100],
    previews: {
      bronze: {
        kind: 'csv',
        path: 'bronze/capacity/2026/08/28/capacity_....csv',
        header: 'coderegion;region;filiere;puismaxinstallee',
        row: '53;Bretagne;Éolien terrestre;1042000',
      },
      silver: {
        kind: 'table',
        path: 'silver/capacity/data.parquet',
        columns: ['region_code', 'source_name', 'puissance_installee_mw', 'annee'],
        row: ['53', 'eolien', 1042.0, 2026],
      },
      gold: {
        kind: 'star',
        fact: {
          table: 'fact_capacity',
          columns: ['id_region', 'id_source', 'puissance_installee_mw', 'annee'],
          row: [8, 2, 1042.0, 2026],
        },
        dims: [
          { table: 'dim_region', columns: ['id_region', 'code_insee', 'nom_region'], row: [8, '53', 'Bretagne'] },
          { table: 'dim_source', columns: ['id_source', 'source_name', 'is_green'], row: [2, 'eolien', 1] },
        ],
      },
      api: { kind: 'api', route: 'GET /v1/capacity/regional?region_code=53' },
    },
  },
  {
    id: 'rte-maintenance',
    label: 'Maintenance réseau (RTE)',
    homepage: 'https://www.services-rte.com',
    lede: [
      { text: 'Toutes les 15 minutes, le ' }, { text: 'JSON', cls: 'tech' }, { text: " brut de l'" }, { text: 'API', cls: 'tech' },
      { text: ' RTE Services, concernant les ' }, { text: 'arrêts et maintenances programmés', cls: 'data' }, { text: ' du réseau, est stocké tel quel dans le ' },
      { text: 'Data Lake', cls: 'storage' }, { text: ', où il est nettoyé. Il est ensuite chargé dans une ' }, { text: 'table', cls: 'tech' },
      { text: ' de la ' }, { text: 'base de données', cls: 'storage' }, { text: ", puis exposé par l'" }, { text: 'API', cls: 'tech' },
      { text: ' et affiché en ' }, { text: 'alerte', cls: 'data' }, { text: ' sur le tableau de bord.' },
    ],
    logo: '/logos/rte.png',
    color: 'var(--color-source-rte)',
    glow: 'var(--color-source-rte-glow)',
    visitedCount: 5,
    dwell: [1300, 1300, 1500, 1100],
    previews: {
      bronze: {
        kind: 'json',
        path: 'bronze/maintenance/2026/08/28/eco2mix_regional_....json',
        data: {
          event_id: 'EVT-20260828-014',
          unit_name: 'GRAVELINES 5',
          event_type: 'Arrêt programmé',
          start_date: '2026-09-01T06:00:00Z',
          end_date: '2026-09-15T18:00:00Z',
          unavailable_mw: 900,
        },
      },
      silver: {
        kind: 'table',
        path: 'silver/maintenance/year=2026/month=09/data.parquet',
        columns: ['event_id', 'unit_name', 'start_date', 'end_date', 'unavailable_mw'],
        row: ['EVT-20260828-014', 'GRAVELINES 5', '2026-09-01T06:00Z', '2026-09-15T18:00Z', 900],
      },
      gold: {
        kind: 'table',
        table: 'fact_maintenance',
        columns: ['event_id', 'unit_name', 'start_date', 'end_date', 'unavailable_mw'],
        row: ['EVT-20260828-014', 'GRAVELINES 5', '2026-09-01T06:00Z', '2026-09-15T18:00Z', 900],
      },
      api: { kind: 'api', route: 'GET /v1/maintenance' },
    },
  },
  {
    id: 'entsoe-price',
    label: 'ENTSO-E Transparency',
    homepage: 'https://transparency.entsoe.eu',
    logo: '/logos/entsoe.svg',
    logoDark: '/logos/entsoe-dark.svg',
    color: 'var(--color-source-price)',
    glow: 'var(--color-source-price-glow)',
    visitedCount: 3,
    dwell: [1300, 1300],
    lede: [
      { text: 'Quotidiennement, le ' }, { text: 'JSON', cls: 'tech' }, { text: " brut de l'" }, { text: 'API', cls: 'tech' },
      { text: ' ENTSO-E, concernant le ' }, { text: 'prix de marché day-ahead', cls: 'data' }, { text: ', est stocké tel quel dans le ' },
      { text: 'Data Lake', cls: 'storage' }, { text: ', où il est nettoyé puis agrégé en table dans la ' }, { text: 'base de données', cls: 'storage' },
      { text: " — pas encore d'" }, { text: 'API', cls: 'tech' }, { text: ' ni de dashboard en direct pour cette donnée : elle sert au ' },
      { text: 'calibrage du seuil « excédent export »', cls: 'data' }, { text: '.' },
    ],
    previews: {
      bronze: {
        kind: 'json',
        path: 'bronze/price/2026/08/28/eco2mix_regional_....json',
        data: {
          timestamp: '2026-08-28T14:00:00+00:00',
          price_eur_mwh: -12.4,
        },
      },
      silver: {
        kind: 'table',
        path: 'silver/price/market/year=2026/month=08/data.parquet',
        columns: ['timestamp', 'price_eur_mwh'],
        row: ['2026-08-28T14:00:00Z', -12.4],
      },
      gold: {
        kind: 'star',
        fact: {
          table: 'fact_market_price',
          columns: ['id_date', 'price_eur_mwh', 'retrieved_at'],
          row: [4821, -12.4, '2026-08-28T14:03:11Z'],
        },
        dims: [
          { table: 'dim_time', columns: ['id_date', 'horodatage', 'heure'], row: [4821, '2026-08-28T14:00:00Z', 14] },
        ],
      },
    },
  },
]

export const CABLE_NOTES = {
  cleaning: {
    label: 'Étape de nettoyage',
    text: "Dépend de la source, mais toujours la même logique : renommage des colonnes, cast des types, dédoublonnage. Un null n'est jamais réécrit à zéro — il veut souvent dire « pas encore publié », pas « valeur nulle » (RTE publie avec quelques minutes de retard).",
  },
  aggregation: {
    label: "Étape d'agrégation",
    text: 'Gold résout les clés étrangères vers les dimensions (région, horodatage, filière) et calcule les métriques dérivées avant de charger la table de faits — la lecture par API se fait ensuite en simple SELECT, sans jointure côté client.',
  },
}
