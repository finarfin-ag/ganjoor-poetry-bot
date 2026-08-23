# Architecture

## Principles

1. Upstream Ganjoor data is read-only input.
2. Original Persian text is never overwritten by normalized text.
3. SQLite is a generated runtime/search artifact, not the canonical archive.
4. Markdown is a portable human-readable export.
5. Telegram is one client of the core, not the core itself.

## Layers

```text
upstream ganjoor-data
        |
        v
importer + validation
        |
        +--> Markdown archive
        |
        +--> SQLite relational tables
                 |
                 +--> FTS5 search index
                 |
                 +--> application service
                           |
                           +--> Telegram UI
                           +--> future HTTP API
                           +--> future web client
```

## Search strategy

Phase 1 uses normalized exact phrase and token search with SQLite FTS5. The original text remains available for display.

Later phases can add:

- prefix and token search
- typo-tolerant/fuzzy lookup
- poet/form/metre filters
- related-poem discovery
- semantic search as an optional separate index
