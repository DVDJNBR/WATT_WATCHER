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
