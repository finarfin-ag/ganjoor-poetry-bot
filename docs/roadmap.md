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
- [ ] Bot skeleton
- [ ] Inline keyboard navigation
- [ ] Search button and conversational search flow
- [ ] Hafez fortune button
- [ ] Random poem / discovery button
- [ ] Poet browser
- [ ] Bookmarks and history
- [ ] Help/about screen

### Search experience
- [ ] Search result cards with poet, work, verse and match type
- [ ] Next/previous pagination
- [ ] Open full poem
- [ ] Search within a selected poet
- [ ] Clearly label approximate/fuzzy matches

### Hafez fortune
- [ ] Select a random Hafez ghazal from the local corpus
- [ ] Return the complete ghazal, not only one verse
- [ ] New fortune button
- [ ] Save/share actions
- [ ] Optional interpretation layer kept separate from the original text

### Discovery
- [ ] Random poem
- [ ] Random verse
- [ ] Browse poets and collections
- [ ] Browse by metre/rhyme later

## Milestone 4 — persistence and personal features

- [ ] Telegram user table
- [ ] Bookmarks
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
