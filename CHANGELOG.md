# Changelog

All notable changes to this project will be documented in this file.

## [1.2.1] - 2026-01-16

### Changed
- **Device Naming:** Updated device name to be just the BGG username (e.g. `seanmccabe`) instead of `BGG Sync {username}` for cleaner integration.
- **Documentation:** Updated README with HACS installation verification and additional details.

## [1.2.0] - 2026-01-11

### Added
- **Force Sync Button:** Added a button entity to manually trigger a synchronisation with BoardGameGeek.
- **Last Sync Sensor:** Added a diagnostic sensor (`bgg_last_sync`) to track the timestamp of the last successful data fetch.
- **String Localization:** Added friendly localised names for the services.
- **Player Details in Recording:** The `record_play` service now supports passing player names, winners, scores, positions, colors, and ratings to BoardGameGeek.
- **Enhanced Recording Metadata:** Added support for `location`, `incomplete`, and `nowinstats` flags in the `record_play` service.

### Changed
- **Asyncio Migration:** Fully migrated network calls to `aiohttp` to prevent thread blocking.
- **Plays Sensor Attributes:** The `last_play` attribute is now "flattened" into top-level attributes on the Plays sensor:
    - `game`
    - `bgg_id`
    - `date`
    - `comment` (Cleaned of BBCode)
    - `expansions` (Extracted from comment text)
    - `winners` (List of winners' names)
    - `players` (List of players' usernames or names)
    - `image` (Fetched from game metadata if available)
    - *NOTE:* The original nested `last_play` attribute dictionary has been removed.
- **Dependencies:** Removed `requests` dependency.
- **Cleaned Up:** Improved code comments and removed unused imports.
- **Removed:** `search_spotify` from the service schema.

### Fixed
- **Clean Attribute Text**: Fixed issue where BGG BBCode tags (e.g. `[thing=...]`) were appearing in sensor attributes (last play comments).
- **Service Stability:** Moved blocking legacy recording logic into an executor job to maintain Home Assistant performance standards while ensuring session persistence.
- **Track Game Service:** Fixed an issue where using the `track_game` service could cause existing sensors to become unavailable if BGG returned a processing status (202).


## [1.1.1] - 2026-01-11

### Changed
- **Branding**: Updated integration name to "BoardGameGeek" for consistency.
- **Timezone Accuracy**: `record_play` service now uses Home Assistant's local time instead of UTC to ensure plays are logged on the correct date.
- **Attribution**: Added "Data provided by BoardGameGeek" attribution to all entities.

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
