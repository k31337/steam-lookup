# steam-lookup

Python script that queries the Steam Web API to show a user's profile, Steam level and badges, bans (VAC/game/community), and their friend list with each friend's ban status.

## Setup

```
pip install -r requirements.txt
cp .env.example .env  # then set your STEAM_API_KEY (https://steamcommunity.com/dev/apikey)
```

## Usage

```
python main.py <steamid64 | vanity_url | profile_url>
```

Example:

```
python main.py gabelogannewell
```

## What it shows

- **Profile**: name, SteamID64, profile URL, status, account creation date, country.
- **Level & Badges**: Steam level and top 5 badges by level.
- **Bans**: VAC bans, game bans, community ban, economy ban.
- **Friends**: total friend count and, for each friend, their name and ban status (VAC/game/community or "clean"). Requires the target's friend list to be public.
