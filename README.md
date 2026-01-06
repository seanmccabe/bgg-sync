# BoardGameGeek Sync (BGG Sync)

A robust Home Assistant custom integration for verifying and tracking BoardGameGeek (BGG) plays and collection data. It creates sensors for your play counts and collection size, and provides a service to record plays directly from Home Assistant.

<a href="https://boardgamegeek.com">
  <img src="https://cf.geekdo-images.com/HZy35cmzmmyV9BarSuk6ug__small/img/gbE7sulIurZE_Tx8EQJXnZSKI6w=/fit-in/200x150/filters:strip_icc()/pic7779581.png" alt="Powered by BoardGameGeek" />
</a>

## Features

*   **Direct API Integration**: Uses the BGG XML API2 directly (no third-party library dependencies) for maximum reliability.
*   **Authentication Support**: Supports BGG's new API Token requirement for data fetching.
*   **Play Recording**: Includes a `bgg_sync.record_play` service to log plays to your BGG account (bypassing the read-only XML API restrictions).
*   **Smart Polling**: Updates every 30 minutes to respect BGG's rate limits and server load.
*   **Multi-User**: Supports tracking multiple BGG accounts.
*   **Game Tracking**: Option to track specific games (by ID) to get dedicated sensors for their play counts.

## Installation

1.  Copy the `bgg_sync` folder into your Home Assistant `custom_components` directory.
2.  Restart Home Assistant.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

*Note: Submission to the default HACS store is coming soon. In the meantime, add this repository as a Custom Repository in HACS.*

## Configuration

1.  Go to **Settings** > **Devices & Services**.
2.  Click **Add Integration** and search for "BGG Sync".
3.  Enter your **BGG Username**.
4.  **API Token (Required for Sensors)**:
    *   Go to [BGG Applications](https://boardgamegeek.com/applications).
    *   Register a new application (e.g., "Home Assistant").
    *   Click "Tokens" and generate a new token.
    *   Paste this token into the configuration dialogue.
5.  **Enable Play Logging**:
    *   Check this box if you want to use the `bgg_sync.record_play` service to log plays to BGG.
6.  **Password**:
    *   Enter your BGG password. This is ONLY required if "Enable Play Logging" is checked.
6.  **Tracked Games**:
    *   Enter a comma-separated list of BGG Game IDs (e.g., `822` for Carcassonne) to create specific sensors for them.

## Sensors

The integration creates the following sensors:

*   `sensor.bgg_sync_{username}_plays`: Total number of plays recorded.
    *   *Attributes*: `last_play_game`, `last_play_date`, `last_play_comment`, `last_play_id`.
*   `sensor.bgg_sync_{username}_collection`: Total number of games in your collection (owned).
*   `sensor.bgg_sync_{username}_plays_{game_id}`: Play count for specific tracked games.

## Services

### `bgg_sync.record_play`

Records a play to your BoardGameGeek account.

**YAML Example:**

```yaml
service: bgg_sync.record_play
data:
  username: "your_bgg_username"
  game_id: 822  # Carcassonne
  date: "2026-01-01"
  length: 60
  comments: "Great game!"
  players:
    - name: "Player One"
      username: "bgg_user_1"
      win: true
    - name: "Player Two"
      username: "bgg_user_2"
      win: false
```

**Arguments:**

*   `username` (Required): The BGG username to log the play for (must be configured in the integration).
*   `game_id` (Required): The BGG ID of the game played.
*   `date` (Optional): Date of the play (YYYY-MM-DD). Defaults to today.
*   `length` (Optional): Duration in minutes.
*   `comments` (Optional): Comments about the play.
*   `players` (Optional): A list of players. Each player can have:
    *   `name`: Display name.
    *   `username`: BGG Username (optional).
    *   `win`: Boolean (true/false) for winner status.

## Troubleshooting

### Sensors show "Unavailable" or 401 Errors
Ensure you have provided a valid **API Token**. BGG has tightened security and now requires this token for most XML API requests. Check your configuration via "Configure" in the Integrations page.

### Play Recording fails
The integration uses a specialised API login method. If you change your password, you must update it in the integration options. If logs show "Login failed," ensure your credentials are correct.


### Enable Debug Logging

To help troubleshoot issues, you can enable debug logging by adding the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.bgg_sync: debug
```

## Future Features (Roadmap)

The following features are planned for upcoming releases:
*   **"Hotness" Sensor**: Track the top trending games on BoardGameGeek.
*   **Wishlist Tracking**: Monitor the size of your Wishlist or "Must Have" list.
*   **User Stats**: Advanced user metrics including H-Index and Trade Rating.
