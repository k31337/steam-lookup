"""Simple client for the Steam Web API."""
import re
import time

import requests

BASE_URL = "https://api.steampowered.com"
INVENTORY_URL = "https://steamcommunity.com/inventory"
MARKET_PRICE_URL = "https://steamcommunity.com/market/priceoverview/"
CS2_APP_ID = 730
USD_CURRENCY = 1
MAX_RETRIES = 4
BACKOFF_BASE_SECONDS = 2


class SteamAPIError(Exception):
    pass


def _request_with_retry(*args, max_retries: int = MAX_RETRIES, **kwargs) -> requests.Response:
    """Wraps requests.get with exponential backoff retries on HTTP 429.

    Honors the Retry-After header when Steam provides one; otherwise backs off
    as BACKOFF_BASE_SECONDS * 2**attempt. Returns the final response (including
    a 429) if retries are exhausted, leaving status-code handling to the caller.
    """
    resp = requests.get(*args, **kwargs)
    attempt = 0
    while resp.status_code == 429 and attempt < max_retries:
        retry_after = resp.headers.get("Retry-After")
        delay = float(retry_after) if retry_after else BACKOFF_BASE_SECONDS * (2 ** attempt)
        time.sleep(delay)
        resp = requests.get(*args, **kwargs)
        attempt += 1
    return resp


class SteamClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise SteamAPIError("Missing Steam API key (STEAM_API_KEY).")
        self.api_key = api_key

    def _get(self, interface: str, method: str, version: str, params: dict) -> dict:
        url = f"{BASE_URL}/{interface}/{method}/{version}/"
        params = {"key": self.api_key, "format": "json", **params}
        resp = _request_with_retry(url, params=params, timeout=10)
        if resp.status_code == 429:
            raise SteamAPIError(f"Rate limited by Steam calling {method}. Try again shortly.")
        if resp.status_code != 200:
            raise SteamAPIError(f"HTTP error {resp.status_code} calling {method}")
        return resp.json()

    def resolve_steam_id(self, identifier: str) -> str:
        """Accepts a SteamID64, a profile URL, or a vanity name and returns the SteamID64."""
        if re.fullmatch(r"\d{17}", identifier):
            return identifier

        vanity = identifier.rstrip("/").split("/")[-1]
        data = self._get(
            "ISteamUser", "ResolveVanityURL", "v1", {"vanityurl": vanity}
        )
        response = data.get("response", {})
        if response.get("success") != 1:
            raise SteamAPIError(f"Could not resolve identifier '{identifier}'.")
        return response["steamid"]

    def get_player_summary(self, steam_id: str) -> dict:
        data = self._get(
            "ISteamUser", "GetPlayerSummaries", "v2", {"steamids": steam_id}
        )
        players = data.get("response", {}).get("players", [])
        if not players:
            raise SteamAPIError(f"No profile found for SteamID {steam_id}.")
        return players[0]

    def get_player_summaries(self, steam_ids: list[str]) -> list[dict]:
        data = self._get(
            "ISteamUser", "GetPlayerSummaries", "v2", {"steamids": ",".join(steam_ids)}
        )
        return data.get("response", {}).get("players", [])

    def get_friend_list(self, steam_id: str) -> list[dict]:
        try:
            data = self._get(
                "ISteamUser", "GetFriendList", "v1",
                {"steamid": steam_id, "relationship": "friend"},
            )
        except SteamAPIError:
            return []
        return data.get("friendslist", {}).get("friends", [])

    def get_player_bans(self, steam_id: str) -> dict:
        data = self._get("ISteamUser", "GetPlayerBans", "v1", {"steamids": steam_id})
        players = data.get("players", [])
        if not players:
            raise SteamAPIError(f"No ban data found for {steam_id}.")
        return players[0]

    def get_players_bans(self, steam_ids: list[str]) -> list[dict]:
        data = self._get(
            "ISteamUser", "GetPlayerBans", "v1", {"steamids": ",".join(steam_ids)}
        )
        return data.get("players", [])

    def get_steam_level(self, steam_id: str) -> int:
        data = self._get(
            "IPlayerService", "GetSteamLevel", "v1", {"steamid": steam_id}
        )
        return data.get("response", {}).get("player_level", 0)

    def get_badges(self, steam_id: str) -> list[dict]:
        data = self._get(
            "IPlayerService", "GetBadges", "v1", {"steamid": steam_id}
        )
        return data.get("response", {}).get("badges", [])

    def get_owned_games(self, steam_id: str) -> list[dict]:
        """Returns owned games with playtime. Requires the game details to be public."""
        data = self._get(
            "IPlayerService", "GetOwnedGames", "v1",
            {"steamid": steam_id, "include_appinfo": 1, "include_played_free_games": 1},
        )
        response = data.get("response", {})
        if not response:
            raise SteamAPIError("Could not retrieve game list (game details are private).")
        return response.get("games", [])

    def get_inventory_item_counts(self, steam_id: str, app_id: int = CS2_APP_ID) -> dict[str, int]:
        """Returns a count of items per item name from a user's public inventory.

        Uses the public community inventory endpoint (no API key required), paginating
        with start_assetid as needed. Raises SteamAPIError if the inventory is private
        or unavailable.

        Note: requesting count=5000 makes Steam return HTTP 400, so pages are capped at
        2000 items and followed via the more_items/last_assetid fields.
        """
        url = f"{INVENTORY_URL}/{steam_id}/{app_id}/2"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; steam-lookup/1.0)"}
        counts: dict[str, int] = {}
        start_assetid = None

        while True:
            params = {"l": "english", "count": 2000}
            if start_assetid:
                params["start_assetid"] = start_assetid

            resp = _request_with_retry(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 403:
                raise SteamAPIError("Inventory is private.")
            if resp.status_code == 400:
                raise SteamAPIError("No inventory data found (empty, private, or game never launched).")
            if resp.status_code == 429:
                raise SteamAPIError("Rate limited by Steam while fetching inventory. Try again shortly.")
            if resp.status_code != 200:
                raise SteamAPIError(f"HTTP error {resp.status_code} fetching inventory.")

            data = resp.json()
            if not data or not data.get("assets"):
                break

            names_by_classid = {
                desc["classid"]: desc.get("market_hash_name") or desc.get("name", "Unknown")
                for desc in data.get("descriptions", [])
            }
            for asset in data["assets"]:
                name = names_by_classid.get(asset["classid"], "Unknown")
                counts[name] = counts.get(name, 0) + int(asset.get("amount", 1))

            if not data.get("more_items"):
                break
            start_assetid = data.get("last_assetid")
            time.sleep(1)

        return counts

    def get_market_price(self, market_hash_name: str, app_id: int = CS2_APP_ID) -> float | None:
        """Returns the lowest market price (in USD) for an item, or None if unavailable.

        Uses the public, unauthenticated priceoverview endpoint. This endpoint is
        aggressively rate-limited by Steam, so callers should space out requests.
        """
        headers = {"User-Agent": "Mozilla/5.0 (compatible; steam-lookup/1.0)"}
        resp = _request_with_retry(
            MARKET_PRICE_URL,
            params={"appid": app_id, "currency": USD_CURRENCY, "market_hash_name": market_hash_name},
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data.get("success"):
            return None
        price_str = data.get("lowest_price") or data.get("median_price")
        if not price_str:
            return None
        match = re.search(r"[\d.,]+", price_str)
        if not match:
            return None
        return float(match.group().replace(",", ""))

    def get_player_achievements(self, steam_id: str, app_id: int) -> list[dict]:
        """Returns achievement progress for a game. Requires the game's stats to be public."""
        url = f"{BASE_URL}/ISteamUserStats/GetPlayerAchievements/v1/"
        params = {"key": self.api_key, "format": "json", "steamid": steam_id, "appid": app_id, "l": "english"}
        resp = _request_with_retry(url, params=params, timeout=10)
        if resp.status_code == 403:
            raise SteamAPIError("Could not retrieve achievements (profile/game stats are private).")
        if resp.status_code == 429:
            raise SteamAPIError("Rate limited by Steam calling GetPlayerAchievements. Try again shortly.")
        if resp.status_code != 200:
            raise SteamAPIError(f"HTTP error {resp.status_code} calling GetPlayerAchievements")

        playerstats = resp.json().get("playerstats", {})
        if not playerstats.get("success"):
            raise SteamAPIError(
                playerstats.get("error") or "Could not retrieve achievements (stats are private or game has none)."
            )
        return playerstats.get("achievements", [])

    def get_game_schema_achievements(self, app_id: int) -> dict[str, dict]:
        """Returns a mapping of achievement apiname -> {displayName, description}."""
        data = self._get("ISteamUserStats", "GetSchemaForGame", "v2", {"appid": app_id, "l": "english"})
        achievements = data.get("game", {}).get("availableGameStats", {}).get("achievements", [])
        return {a["name"]: a for a in achievements}

    def get_inventory_value(
        self, item_counts: dict[str, int], app_id: int = CS2_APP_ID, max_unique_items: int = 30,
        request_delay: float = 1.0, on_item_priced=None,
    ) -> tuple[float, int]:
        """Estimates total inventory value in USD by pricing the most common items.

        Returns (total_value, priced_unique_item_count). To respect Steam's rate
        limits, only the top `max_unique_items` (by quantity) are priced.

        If provided, `on_item_priced(index, total, name)` is called after each
        item lookup (e.g. to drive a progress bar).
        """
        top_items = sorted(item_counts.items(), key=lambda kv: kv[1], reverse=True)[:max_unique_items]
        total_value = 0.0
        priced_count = 0
        for i, (name, count) in enumerate(top_items):
            price = self.get_market_price(name, app_id)
            if price is not None:
                total_value += price * count
                priced_count += 1
            if on_item_priced:
                on_item_priced(i + 1, len(top_items), name)
            if i < len(top_items) - 1:
                time.sleep(request_delay)
        return total_value, priced_count
