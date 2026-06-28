# steam-lookup

[![Tests](https://github.com/k31337/steam-lookup/actions/workflows/tests.yml/badge.svg)](https://github.com/k31337/steam-lookup/actions/workflows/tests.yml)

A Python CLI tool that queries the [Steam Web API](https://steamcommunity.com/dev) to display a player's profile, Steam level and badges, owned games and playtime, VAC/game/community bans, estimated CS2 inventory value, and their friend list with each friend's ban status.

## Requirements

- Python 3.10+
- A Steam Web API key

## Setup

1. Clone the repository and install dependencies:

   ```
   pip install -r requirements.txt
   ```

2. Get a Steam Web API key from [steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey) (a domain is required to register a key; `localhost` works for local use).

3. Copy the example environment file and add your key:

   ```
   cp .env.example .env
   ```

   Edit `.env`:

   ```
   STEAM_API_KEY=your_api_key_here
   ```

   > **Never commit `.env`.** It is already excluded via `.gitignore`. Only `.env.example` (with a placeholder value) should be tracked in version control.

## Usage

```
python main.py <steamid64 | vanity_url | profile_url>
```

Accepts any of the following identifier formats:

- A 17-digit SteamID64, e.g. `76561197960287930`
- A vanity name, e.g. `gabelogannewell`
- A full profile URL, e.g. `https://steamcommunity.com/id/gabelogannewell/`

### Example

```
python main.py gabelogannewell
```

### Comparing two profiles

Show the friends two profiles have in common:

```
python main.py <identifier_a> --compare <identifier_b>
```

### Exporting results

Save all collected data (profile, level, badges, games, bans, inventory, friends, trust score) as JSON:

```
python main.py <identifier> --export results.json
```

### Game achievements

Show achievement progress for a specific game (requires the profile's game stats to be public):

```
python main.py <identifier> --achievements <appid>
```

Example (CS2):

```
python main.py <identifier> --achievements 730
```

## What it shows

| Section          | Data                                                                                  | Source endpoint                                          |
|------------------|----------------------------------------------------------------------------------------|------------------------------------------------------------|
| Profile          | Name, SteamID64, profile URL, online status, account creation date, country            | `ISteamUser/GetPlayerSummaries`                             |
| Level & Badges   | Steam level, total badge count, top 5 badges by XP                                     | `IPlayerService/GetSteamLevel`, `GetBadges`                 |
| Games            | Owned game count, total playtime, top 5 games by playtime                              | `IPlayerService/GetOwnedGames`                              |
| Bans             | VAC bans, game bans, community ban, economy ban, days since last ban                   | `ISteamUser/GetPlayerBans`                                  |
| CS2 Inventory    | Total/unique item counts, top 5 items, estimated value in USD                          | Public inventory endpoint + Steam Market price overview     |
| Friends          | Total friend count; each friend's name and ban status (VAC/game/community or "clean"), shown in paginated tables of 25 | `ISteamUser/GetFriendList`, `GetPlayerBans`  |
| Trust Assessment | A 0-100 heuristic score with reasons (bans, account age, profile/games/inventory/friends privacy) | Computed locally from the data above                |
| Achievements (`--achievements`) | Unlock progress for a specific game: unlocked/total, unlock dates, locked achievements | `ISteamUserStats/GetPlayerAchievements`, `GetSchemaForGame` |

> **Trust Assessment is not an official Valve signal.** It's a simple local heuristic meant for quick orientation, not a definitive verdict — always use your own judgment.

Some sections depend on the target's privacy settings and are skipped with a notice if unavailable:
- **Games** requires "game details" to be public.
- **CS2 Inventory** requires the inventory to be public.
- **Friends** requires the friend list to be public.

## Project structure

```
.
├── main.py                       # CLI entry point and output formatting
├── steam_api.py                   # Steam Web API client
├── tests/                         # Unit tests (mocked, no network calls)
├── .github/workflows/tests.yml    # CI: runs the test suite on push/PR
├── requirements.txt               # Runtime dependencies
├── requirements-dev.txt           # Runtime + test dependencies
├── .env.example                   # Template for required environment variables
└── README.md
```

## Running tests

Tests are fully mocked and make no real network calls.

```
pip install -r requirements-dev.txt
pytest
```

## Notes

- This project uses the official Steam Web API and is not affiliated with or endorsed by Valve.
- API keys are personal and tied to your Steam account — do not share or commit them.
- If Steam responds with HTTP 429 (rate limited), requests are automatically retried with exponential backoff (honoring the `Retry-After` header when present) before giving up.

## License

Distributed under the terms of the [MIT License](LICENSE).
