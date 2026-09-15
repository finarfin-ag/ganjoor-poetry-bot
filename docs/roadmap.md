# Roadmap

## Milestone 1 — corpus core

- [x] Project structure
- [x] Persian normalization
- [x] SQLite schema
- [x] FTS5 search layer
- [x] Markdown exporter
- [x] Initial tests
- [x] Validate against current ganjoor-data snapshot
- [ ] Pin and record upstream commit SHA
- [x] Build full database and corpus statistics
- [x] Benchmark common Persian queries

Current validated VPS corpus: 240 poets, 2,292 categories, 135,319 poems, 3,088,247 verses.

## Milestone 2 — search quality

- [x] Search modes: phrase / all words / any word
- [x] Filters by poet/category
- [ ] Filter by metre/rhyme
- [ ] Highlight matching text
- [ ] Prefix search
- [x] Typo-tolerant / fuzzy search prototype
- [ ] Optimize fuzzy-search latency for interactive bot use
- [x] Persian spacing variants for می/نمی
- [x] Distinguish exact/all/fuzzy match types
- [x] Keep AI-generated summaries out of primary-text attribution

## Milestone 3 — Telegram and user experience

### Main menu
- [x] Bot skeleton
- [x] Inline keyboard navigation
- [x] Search button and conversational search flow
- [x] Hafez fortune button
- [ ] Random poem / discovery button backend
- [x] Poet browser backend
- [x] Bookmarks backend
- [x] Help/about screen

### Search experience
- [x] Search result cards with poet, work, verse and match type
- [ ] Search-result next/previous pagination
- [x] Open full poem from the poet/work browser
- [x] Open full poem directly from search results
- [ ] Search within a selected poet
- [x] Clearly label approximate/fuzzy matches
- [x] Keep fast exact/all search separate from slower fuzzy fallback

### Hafez fortune
- [x] Select a random Hafez ghazal from the local corpus
- [x] Return the complete ghazal, not only one verse
- [x] New fortune button
- [x] Save/share actions
- [ ] Optional interpretation layer kept separate from the original text

### Discovery and browsing
- [ ] Random poem
- [ ] Random verse
- [x] Browse paginated poet list
- [x] Show poem count per poet
- [x] Browse category/subcategory tree
- [x] Browse paginated works in a category
- [x] Browse all works by poet
- [x] Open complete original text of an individual work
- [ ] Browse by metre/rhyme later

## Milestone 4 — persistence and personal features

- [x] Telegram user table
- [x] Bookmarks
- [x] User-defined bookmark collections
- [x] Move bookmarks between collections
- [x] Rename/delete bookmark collections
- [x] Separate bot-state database from the poetry corpus
- [ ] Search history
- [ ] Recent fortunes
- [ ] User preferences
- [ ] Safe migration/versioning for bot-state database

## Milestone 5 — deployment

- [ ] Docker image
- [ ] systemd or Docker Compose deployment
- [ ] VPS backup strategy
- [x] GitHub Actions CI
- [ ] Optional automated deployment
- [ ] Health check and structured logs
