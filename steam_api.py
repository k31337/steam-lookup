"""Simple client for the Steam Web API."""
import re
import requests

BASE_URL = "https://api.steampowered.com"


class SteamAPIError(Exception):
    pass


class SteamClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise SteamAPIError("Missing Steam API key (STEAM_API_KEY).")
        self.api_key = api_key

    def _get(self, interface: str, method: str, version: str, params: dict) -> dict:
        url = f"{BASE_URL}/{interface}/{method}/{version}/"
        params = {"key": self.api_key, "format": "json", **params}
        resp = requests.get(url, params=params, timeout=10)
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
