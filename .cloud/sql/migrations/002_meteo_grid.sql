-- Grille météo open-meteo 22×16 = 352 points couvrant la France
-- Pipeline écrit toutes les 15 min via UPSERT, pas d'historique

create table if not exists meteo_grid (
  lat            double precision not null,
  lon            double precision not null,
  cloud_cover    smallint         not null default 0,  -- % 0-100
  wind_speed     real             not null default 0,  -- m/s
  wind_direction smallint         not null default 0,  -- degrés 0-360
  updated_at     timestamptz      not null default now(),
  primary key (lat, lon)
);

comment on table meteo_grid is
  'Grille météo 22×16 (lon -5→10.75, lat 41→52.25, pas 0.75°). '
  'Écrasée toutes les 15 min par le pipeline Azure Function.';

-- Index pour requêtes bbox si besoin futur
create index if not exists meteo_grid_lat_lon on meteo_grid (lat, lon);

-- RLS : lecture publique (anon key), écriture réservée service_role
alter table meteo_grid enable row level security;

create policy "meteo_grid_read_public"
  on meteo_grid for select
  using (true);
