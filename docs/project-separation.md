# Project separation

This repository originally held two unrelated scraping experiments. They now have independent code, dependencies, tests, documentation, and generated data.

## What happened

- Commit `bae478941dc51b6de64f04030b7d33012e0fe635` (March 17, 2025) introduced the Zer4U scripts. Its `autoscrap.py` traversed category pages with `bscrp` and handled lazy-loaded images.
- Commit `860f7bc7f1d7454ffd7885d2561cc6ce260cdb9d` (March 23, 2025, rewritten during contact-data removal) replaced that `autoscrap.py` with 11888 code and added two more phonebook crawlers and a CSV exporter. Its original version also committed a contact database, which has since been removed from branch history.
- The cleanup consolidates Zer4U's original listing, detail, and pagination approaches into the `zer4u` package. The existing [11888-scrapper repository](https://github.com/NimLordia/11888-scrapper) contains the 11888 parser, bounded URL-list and sequential-range runner, and CSV export.

## File ownership

| Original file | Project | Replacement |
| --- | --- | --- |
| `scrap.py` | Zer4U | Optional product detail parsing |
| `scrap2.py` | Zer4U | Product listing parsing |
| `autoscrap.py` at `bae4789` | Zer4U | Bounded category pagination and scrolling |
| `autoscrap.py` at `860f7bc` | 11888 | Bounded phonebook runner |
| `phoneScrap.py`, `scrapAll.py` | 11888 | Bounded phonebook runner |
| `sqliteToCSV.py` | 11888 | Streaming CSV export |
| `products.db`, `zer4u_products*.db` | Zer4U | Generated local output, ignored by Git |
| `11888_data.db` | 11888 | Excluded; use synthetic demo fixtures |

## Compatibility and data

Old script names are retired. Use each project's documented module entrypoint. The original source remains available in the Git commits above.

Zer4U upserts by source URL; 11888 deduplicates unchanged contact snapshots. Use a new database path; old experiment databases are not migrated automatically. Their tracked snapshots are removed from the current project files. No contact records are copied into the cleaned project.

The contact database was removed from the published branch histories of both repositories on September 14, 2026. Old clones must be replaced or cleaned before their work is pushed again. GitHub may retain cached copies of old commits and pull-request objects; purging those requires GitHub Support. The history rewrite alone does not erase every previously published copy.

Live site compatibility was not verified during this cleanup. Fixtures demonstrate the parser and storage behavior using synthetic data and the original selectors.
