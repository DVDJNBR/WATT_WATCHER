# Logos des sources de données

Affichés dans l'onglet Pipeline, à côté du nom de chaque source. Usage
nominatif : on cite d'où vient la donnée, on ne revendique aucun partenariat.

| Fichier | Source | Provenance | Licence |
|---|---|---|---|
| `rte.png` | RTE eCO2mix | `odre.opendatasoft.com/assets/theme_image/logo-rte-v4.png` | marque RTE |
| `open-meteo.png` | Open-Meteo | `open-meteo.com/favicon.ico`, converti en PNG | marque Open-Meteo |
| `entsoe.svg` | ENTSO-E Transparency | Wikimedia Commons — *Logo European Transmission System Operators.svg* | domaine public |
| `odre.svg` | ODRE | `odre.opendatasoft.com/assets/theme_image/logo-odre.svg` | marque ODRE |

## Variantes thème sombre

Les quatre logos ont un fond transparent d'origine. Deux sont encrés trop
sombre pour tenir sur `#19191c` : ENTSO-E (bleus `#282e70` à `#4c57b0`) et ODRE
(ardoise `#283943`). `entsoe-dark.svg` et `odre-dark.svg` reprennent les mêmes
fichiers avec ces encres éclaircies — teinte et saturation conservées, seule la
clarté est remontée, donc la marque reste elle-même. Les accents de couleur
(l'or `#fabd17` d'ENTSO-E, le turquoise `#01ABB0` d'ODRE) ne sont pas touchés.

RTE et Open-Meteo n'ont pas de variante : luminance d'encre mesurée à 137/255,
lisible sur les deux fonds.

Récupérés le 2026-10-01. Servis depuis `frontend/public/logos/`, jamais en lien
direct vers le serveur d'origine : pas de hotlink, et la page ne dépend pas de
la disponibilité d'un site tiers.

## Icônes de services Azure — `azure/`

Le schéma d'architecture de l'onglet Pipeline utilise les icônes officielles
Microsoft, et non des pictogrammes redessinés : un recruteur qui connaît Azure
reconnaît un compte de stockage au premier regard.

| Fichier | Icône d'origine | Rôle dans le schéma |
|---|---|---|
| `storage-accounts.svg` | `Icons/storage/10086-icon-service-Storage-Accounts.svg` | le compte ADLS Gen 2 |
| `storage-container.svg` | `Icons/general/10839-icon-service-Storage-Container.svg` | les conteneurs Bronze, Silver, Gold |
| `function-apps.svg` | `Icons/compute/10029-icon-service-Function-Apps.svg` | l'API REST et les minuteries d'ingestion |
| `sql-server.svg` | `Icons/databases/10132-icon-service-SQL-Server.svg` | le serveur logique qui héberge la base |
| `sql-database.svg` | `Icons/databases/10130-icon-service-SQL-Database.svg` | la base Gold, schéma en étoile |
| `static-web-apps.svg` | `Icons/web/01007-icon-service-Static-Apps.svg` | le dashboard servi au visiteur |
| `dashboard.svg` | `Icons/general/10015-icon-service-Dashboard.svg` | le dashboard lui-même, dans le Static Web App |

Jeu « Azure architecture icons », version V24, téléchargé le 2026-10-01 depuis
`arch-center.azureedge.net/icons/Azure_Public_Service_Icons_V24.zip`, lien publié
sur `learn.microsoft.com/azure/architecture/icons/`. Conditions d'utilisation
reprises dans `Microsoft_Terms_of_Use.pdf` : gratuites pour documenter une
architecture, interdiction de les modifier, interdiction de s'en servir pour
suggérer un lien avec Microsoft. Les fichiers sont donc copiés **tels quels** —
aucune couleur retouchée, aucun tracé simplifié. Seule la taille d'affichage
change, par CSS.

Conséquence de cette interdiction : les trois conteneurs portent la même icône
bleue. Ce qui distingue Bronze, Silver et Gold est posé autour de l'icône, par
un filet de couleur sur la rangée, pas dans le fichier.

Il n'existe pas d'icône « Data Lake Storage Gen2 » dans le jeu : seule la Gen1 y
figure, et elle est obsolète. ADLS Gen 2 est un compte de stockage avec espace
de noms hiérarchique, donc `Storage-Accounts` est le mark correct.

Le choix de `Function-Apps` n'est pas un raccourci : `functions/function_app.py`
instancie `func.FunctionApp()` et déclare chaque route en `@app.route(...)`.
L'API v1 est un déclencheur HTTP, pas une passerelle gérée. Afficher
`API-Management-Services` ferait croire à un service qui n'a jamais été
provisionné.

Gold n'est pas un conteneur ADLS : `functions/shared/gold/fact_loader.py` lit le
Parquet Silver et fait des `INSERT` dans `FACT_ENERGY_FLOW`. L'étape est
relationnelle, d'où une icône de base de données et non de conteneur. Le compte
de stockage s'arrête donc à deux conteneurs, Bronze et Silver.
