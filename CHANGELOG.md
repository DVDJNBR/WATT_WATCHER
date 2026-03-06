## [1.4.0](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.3.4...v1.4.0) (2026-03-06)

### Features

* **dashboard:** add date range picker, empty state, and visual polish ([9b5f946](https://github.com/DVDJNBR/WATT_WATCHER/commit/9b5f946f70f120d719ebef6b83b096bd0c736a1a))

## [1.3.4](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.3.3...v1.3.4) (2026-03-06)

### Bug Fixes

* **deps:** add pyodbc to Azure Function requirements ([babf1b9](https://github.com/DVDJNBR/WATT_WATCHER/commit/babf1b941d6144ccce474316f2c1a954fd58af79))

## [1.3.3](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.3.2...v1.3.3) (2026-03-05)

### Bug Fixes

* **deps:** add pyarrow to Azure Function requirements ([cd4a44b](https://github.com/DVDJNBR/WATT_WATCHER/commit/cd4a44b86502b50fcc8fd94dbd04d4f417d7df2f))

## [1.3.2](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.3.1...v1.3.2) (2026-03-05)

### Bug Fixes

* **pipeline:** create SQL Server schema on first run + download bronze from ADLS for silver stage ([dcdab1b](https://github.com/DVDJNBR/WATT_WATCHER/commit/dcdab1bf61329d1fc752d0303048ea74fb078d1f))

## [1.3.1](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.3.0...v1.3.1) (2026-03-05)

### Bug Fixes

* **api:** use TOP(?) for SQL Server instead of LIMIT (SQLite-only syntax) ([19f1e84](https://github.com/DVDJNBR/WATT_WATCHER/commit/19f1e84b3d08eab0f3ffa626dd1dd8ad2190799f))

## [1.3.0](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.2.12...v1.3.0) (2026-03-05)

### Features

* **auth:** replace JWT/Azure AD with API key authentication ([3e96b1e](https://github.com/DVDJNBR/WATT_WATCHER/commit/3e96b1ebd8e17e3d90dc4968b97816abfd578e5c))

## [1.2.12](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.2.11...v1.2.12) (2026-03-04)

### Bug Fixes

* **terraform:** provision SQL_CONNECTION_STRING in function app settings ([8e19b10](https://github.com/DVDJNBR/WATT_WATCHER/commit/8e19b1002d2d55857f81ff7d7931a2804ce6dbcf))

## [1.2.11](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.2.10...v1.2.11) (2026-03-04)

### Bug Fixes

* resolve ~40 Pyright type-checking errors across 10 files ([1ff50e5](https://github.com/DVDJNBR/WATT_WATCHER/commit/1ff50e5c04924412a36e1fff57cbc4b9fd85c166))

## [1.2.10](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.2.9...v1.2.10) (2026-03-03)

### Bug Fixes

* correct all bad absolute imports and add AzureWebJobsFeatureFlags ([56c30ae](https://github.com/DVDJNBR/WATT_WATCHER/commit/56c30aeba8d5e2934c6e6cda25bc4eaddaad30e9))
* **deploy:** switch to Oryx remote build now that polars is removed ([cd81d4c](https://github.com/DVDJNBR/WATT_WATCHER/commit/cd81d4c4c4f6565870917d5c079f8bbd050877f5))
* **terraform:** add AzureWebJobsFeatureFlags to infra definition ([4fdb1ef](https://github.com/DVDJNBR/WATT_WATCHER/commit/4fdb1eff906a9bcf9eef1feb47edf000bf47d145))

## [1.2.9](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.2.8...v1.2.9) (2026-03-03)

## [1.2.8](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.2.7...v1.2.8) (2026-03-03)

### Bug Fixes

* **deploy:** pre-install 7 packages on CI — polars kills Oryx even alone ([2d2e035](https://github.com/DVDJNBR/WATT_WATCHER/commit/2d2e035b60c1b597118fb549b25c4ce006c70e63))

## [1.2.7](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.2.6...v1.2.7) (2026-03-03)

### Bug Fixes

* **deploy:** isolate Azure Functions deps in functions/requirements.txt ([b0f0dfe](https://github.com/DVDJNBR/WATT_WATCHER/commit/b0f0dfe01e9c23357fe2ed1894a0c33ae555a656))

## [1.2.6](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.2.5...v1.2.6) (2026-03-03)

### Bug Fixes

* **deploy:** native pip install instead of cross-platform --platform flag ([480bf57](https://github.com/DVDJNBR/WATT_WATCHER/commit/480bf570358cdf75ec24252989b62fd12f024e20))

## [1.2.5](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.2.4...v1.2.5) (2026-03-03)

### Bug Fixes

* **deploy:** use manylinux_2_28 platform — pyarrow 23.x dropped manylinux2014 ([ed897ef](https://github.com/DVDJNBR/WATT_WATCHER/commit/ed897efaf6cf8b904f58261e5f141b193cd1da22))

## [1.2.4](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.2.3...v1.2.4) (2026-03-03)

### Bug Fixes

* **deploy:** pre-install manylinux2014 wheels to bypass Oryx memory limit ([ad89a5b](https://github.com/DVDJNBR/WATT_WATCHER/commit/ad89a5baa35f14d676507db681ab62bbbe5be910))

## [1.2.3](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.2.2...v1.2.3) (2026-03-03)

### Bug Fixes

* **deploy:** Oryx remote build only — no local .python_packages ([8643ddb](https://github.com/DVDJNBR/WATT_WATCHER/commit/8643ddbd7208452a22ac0be3e44e6d8d88303f77))

## [1.2.2](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.2.1...v1.2.2) (2026-03-03)

### Bug Fixes

* **deploy:** pre-install deps locally for Linux Consumption plan ([c101a73](https://github.com/DVDJNBR/WATT_WATCHER/commit/c101a73afcd8cef8904534c8b6bf77528a208c60))

## [1.2.1](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.2.0...v1.2.1) (2026-03-03)

### Bug Fixes

* **deploy:** set package root to functions/ — function_app.py was not at ZIP root ([ee08637](https://github.com/DVDJNBR/WATT_WATCHER/commit/ee0863752127fca40584b9c7b8c77c495ce4c1b3))

## [1.2.0](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.1.3...v1.2.0) (2026-03-02)

### Features

* **5.2:** merge Over-Production & Negative Price Alerts ([b203839](https://github.com/DVDJNBR/WATT_WATCHER/commit/b203839d0366d650fe085e10bcebcff4670b54d6))
* **5.2:** Over-Production & Negative Price Alerts ([a133ac3](https://github.com/DVDJNBR/WATT_WATCHER/commit/a133ac3947a6e720351f4345ad82408e7e281434))

## [1.1.3](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.1.2...v1.1.3) (2026-03-02)

### Bug Fixes

* **gold:** bulk-load fact_loader with staging table + fix test failures ([9d0b782](https://github.com/DVDJNBR/WATT_WATCHER/commit/9d0b78293404ba094b31463dc3b7ed5073fdb685)), closes [#stg](https://github.com/DVDJNBR/WATT_WATCHER/issues/stg)

## [1.1.2](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.1.1...v1.1.2) (2026-03-01)

### Bug Fixes

* **deploy:** replace Azure SWA with Storage static website (student sub restriction) ([2033d14](https://github.com/DVDJNBR/WATT_WATCHER/commit/2033d144babb6ce490bb54cb5981f4315768f211))

## [1.1.1](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.1.0...v1.1.1) (2026-02-28)

## [1.1.0](https://github.com/DVDJNBR/WATT_WATCHER/compare/v1.0.0...v1.1.0) (2026-02-28)

### Features

* **7.0:** Azure deployment — full pipeline, SWA, deploy workflow ([b600b20](https://github.com/DVDJNBR/WATT_WATCHER/commit/b600b20e1e437d1551d9ee667f73c7894118c68f))

## 1.0.0 (2026-02-28)

### Features

* **0.1:** API exploration & schema discovery ([164b351](https://github.com/DVDJNBR/WATT_WATCHER/commit/164b351e448d4d7728360b33191c21459c6fb7b1))
* **1.0:** Infrastructure as Code with Terraform ([dbc0013](https://github.com/DVDJNBR/WATT_WATCHER/commit/dbc0013ca948b8cdaafb8e0e5044faae84ba4f5b))
* **1.1:** RTE eCO2mix API ingestion pipeline ([374dc47](https://github.com/DVDJNBR/WATT_WATCHER/commit/374dc476ad85a2768b66e331c1eeec8e0f5f642a))
* **1.2:** CSV capacity ingestion pipeline ([8f2f9e8](https://github.com/DVDJNBR/WATT_WATCHER/commit/8f2f9e86fba1bf335054eef5fd0c6942624149cf))
* **1.3:** dynamic asset discovery & lifecycle management ([65d5bd1](https://github.com/DVDJNBR/WATT_WATCHER/commit/65d5bd1741ea0e95843f706f65466e907d89edb9))
* **2.1:** web scraping grid maintenance portals ([7a31102](https://github.com/DVDJNBR/WATT_WATCHER/commit/7a31102e3be2cb32f12786e7988d0c13f118ad49))
* **2.2:** ERA5 climate Parquet ingestion with Polars streaming ([47fe5c3](https://github.com/DVDJNBR/WATT_WATCHER/commit/47fe5c30c3e5cfa3a3b46710ce5410934712267c))
* **2.3:** government emission factor ingestion ([18212aa](https://github.com/DVDJNBR/WATT_WATCHER/commit/18212aa5345a56b3f530f36fde02954333e717df)), closes [#3](https://github.com/DVDJNBR/WATT_WATCHER/issues/3) [#2](https://github.com/DVDJNBR/WATT_WATCHER/issues/2)
* **3.1:** Bronze→Silver transformation layer ([05789e9](https://github.com/DVDJNBR/WATT_WATCHER/commit/05789e989e223f96d53f6d8c1bb583d2b6a252f3))
* **3.2:** Silver→Gold Star Schema + lint cleanup ([b6d0cda](https://github.com/DVDJNBR/WATT_WATCHER/commit/b6d0cda4812b6f6a651bee8021a6c8509e1520f2))
* **3.3:** data quality gates — config-driven integrity checks ([aaf0501](https://github.com/DVDJNBR/WATT_WATCHER/commit/aaf0501ce28ba6eda54446116166894518b50ec9))
* **4.1:** Production API endpoints & CSV export ([21e4f97](https://github.com/DVDJNBR/WATT_WATCHER/commit/21e4f97f3197b397f28ba7ba4a68ec5a468e201a))
* **4.2:** Azure AD JWT security implementation ([c3ddce4](https://github.com/DVDJNBR/WATT_WATCHER/commit/c3ddce40b35d9cdbc2a49c529a224e6025f49f1e))
* **4.3:** Automated Swagger/OpenAPI Documentation & code quality fixes ([b7dc0e5](https://github.com/DVDJNBR/WATT_WATCHER/commit/b7dc0e5b5691c840ff50de26a0a4b5a99fbe78cf))
* **5.1:** Grid Monitoring Dashboard — Vite + React frontend ([573ef74](https://github.com/DVDJNBR/WATT_WATCHER/commit/573ef749b66549ea6055f09aabaa696a8db83aa3))
* **6.1-6.2:** Epic 6 discovery — data brief, UX spec, benchmark & regulatory stories ([718a88d](https://github.com/DVDJNBR/WATT_WATCHER/commit/718a88de4d1483066172bc052ed04d7514a7d368))

### Bug Fixes

* **5.1:** code review fixes — 58 Vitest tests passing ([90fbecf](https://github.com/DVDJNBR/WATT_WATCHER/commit/90fbecfc4536e3a3a9459e8453e04ae5efcfb611))
* **5.1:** data pipeline, API aggregation, port 8765 & Pyright fixes ([65458e6](https://github.com/DVDJNBR/WATT_WATCHER/commit/65458e608e508f9b68f63b5db55ca8a523e78c79))
* correct _bmad gitignore pattern to _bmad/ ([7cdc259](https://github.com/DVDJNBR/WATT_WATCHER/commit/7cdc25970a4eef06b0161856bead8cfaf97547eb))
* resolve Pyright lint errors in ERA5 modules ([f3631bd](https://github.com/DVDJNBR/WATT_WATCHER/commit/f3631bd633854ac8d19a98346885af2825b62c71))
* resolve Pyright type errors in quality checks ([639a119](https://github.com/DVDJNBR/WATT_WATCHER/commit/639a119ae0b552bc9abeedf5c9611cee5226404b))
* **tests:** update test_api_endpoints to match new pagination logic ([e48acc2](https://github.com/DVDJNBR/WATT_WATCHER/commit/e48acc28a4eedbcc3cbe4944b3d97abd90021b3c))
