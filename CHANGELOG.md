# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-01-10

### Added
- **Collection Tracking**: New option to track your entire BGG collection as individual sensors.
- **Rich Metadata Refinement**: Added parsing for `min_players`, `max_players`, `min_playtime`, `max_playtime`, `sub_type`, `year`, `rank`, `weight`.
- **Game Tracking Service**: Enhanced `bgg_sync.track_game` service to support adding `nfc_tag` and `music` attributes to specific games.
- **Dynamic Icons**: Game sensors now display the game's box art (via `entity_picture`) if available, falling back to the dice icon.
- **Configuration**: Added "Track Collection" toggle in Options Flow.

### Changed
- **API Performance**: Optimized batch sizing (reduced to 20) for BGG API requests to prevent "400 Bad Request" errors on large collections.
- **Translations**: Improved UI labels for configuration options.
- **Attributes**: Renamed `subtype` to `sub_type` and fixed `coll_id` to only appear when relevant.
- **Reliability**: Achieved 100% test coverage and implemented strict linting (ruff) to ensure robustness and code quality.

### Fixed
- Fixed issue where game attributes (Weight, Rating, etc.) were showing as "Unknown" due to XML parsing errors.
- Fixed issue where service calls to `track_game` with `tag` or `playlist` aliases were ignored (now strictly `nfc_tag` and `music`).
- Fixed multi-user collection tracking support.

## [1.0.0] - 2024-01-01

### Added
- Initial Release.
- Basic BGG user stats (Plays, Collection Count).
- `record_play` service.
- Todo list integration.
