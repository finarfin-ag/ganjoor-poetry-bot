# Ganjoor Poetry Bot

An open-source Persian poetry data pipeline and Telegram bot built on top of the public Ganjoor corpus.

The project keeps source data, a human-readable Markdown archive, and a rebuildable SQLite + FTS5 search database separate from the Telegram interface.

## Goals

- Import the Ganjoor corpus from `ganjoor/ganjoor-data`.
- Preserve the original Persian text.
- Build a normalized search representation for Persian/Arabic character variants, diacritics, whitespace, and ZWNJ.
- Export poems as Markdown for long-term, tool-independent archival use.
- Build a SQLite database with FTS5 for fast full-text search.
- Provide a clean core that can later power Telegram, a website, Android clients, research tools, and APIs.

## Planned features

- Full-text search across all poems
- Exact-phrase and multi-word search
- Poet and collection filtering
- Hafez fortune (`فال حافظ`)
- Random poem / verse discovery
- Bookmarks and history at the client layer
- Meter and rhyme filtering where source metadata is available
- Future fuzzy search for imperfectly remembered verses

## Architecture

```text
Ganjoor data
     |
     v
Importer + Persian normalization
     |
     +----> Markdown archive
     |
     +----> SQLite + FTS5
                  |
                  v
             Poetry Core
          /       |       \
     Telegram    Web      API
```

## Development status

Milestone 1: data pipeline and search foundation.

The Telegram layer is intentionally postponed until the corpus importer and search behavior are reliable.

## Source data

This project is designed around the public `ganjoor/ganjoor-data` repository. The generated database is treated as a rebuildable artifact rather than the canonical source of truth.

See `NOTICE.md` before redistributing corpus content. Individual texts or modern editions may have rights or attribution requirements independent of this project's source-code license.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

# Put or clone ganjoor-data under data/ganjoor-data, then:
python scripts/build_database.py \
  --source data/ganjoor-data \
  --database data/poetry.sqlite \
  --markdown data/markdown

pytest
```

## Repository layout

```text
src/ganjoor_bot/    Core Python package
schema/              SQLite/FTS schema
scripts/             Fetch/build utilities
tests/               Normalization/import/search tests
docs/                Architecture and roadmap
data/                 Generated/local data (gitignored)
```

## License

Project source code is licensed under the GNU Affero General Public License v3.0. Corpus data remains subject to its original sources and applicable rights.
