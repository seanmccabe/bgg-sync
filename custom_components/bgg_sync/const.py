"""Constants for the BGG Sync integration."""

DOMAIN = "bgg_sync"
BGG_URL = "https://boardgamegeek.com"
BASE_URL = f"{BGG_URL}/xmlapi2"

CONF_PLAYERS = "players"
CONF_BGG_USERNAME = "bgg_username"
CONF_BGG_PASSWORD = "bgg_password"
CONF_API_TOKEN = "bgg_api_token"
CONF_GAMES = "games"
CONF_ENABLE_LOGGING = "enable_logging"

ATTR_LAST_PLAY = "last_play"
ATTR_TOTAL_PLAYS = "total_plays"
ATTR_TOTAL_COLLECTION = "total_collection"

SERVICE_RECORD_PLAY = "record_play"
SERVICE_TRACK_GAME = "track_game"

# Game Metadata
CONF_NFC_TAG = "nfc_tag"
CONF_MUSIC = "music"
CONF_CUSTOM_IMAGE = "custom_image"
CONF_GAME_DATA = "game_data" # To store the rich metadata dict

ATTR_GAME_RANK = "rank"
ATTR_GAME_YEAR = "year"
ATTR_GAME_WEIGHT = "weight"
ATTR_GAME_PLAYING_TIME = "playing_time"
