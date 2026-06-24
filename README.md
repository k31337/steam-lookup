# steam-lookup

Python script that queries the Steam Web API to show a user's profile, friend list, and bans (VAC/game/community).

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
