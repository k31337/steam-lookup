from unittest.mock import patch

import pytest

from steam_api import SteamAPIError, SteamClient


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


@pytest.fixture
def client():
    return SteamClient(api_key="fake-key")


def test_missing_api_key_raises():
    with pytest.raises(SteamAPIError):
        SteamClient(api_key="")


def test_resolve_steam_id_with_steamid64_passthrough(client):
    assert client.resolve_steam_id("76561197960287930") == "76561197960287930"


def test_resolve_steam_id_with_vanity_name(client):
    fake = FakeResponse(200, {"response": {"success": 1, "steamid": "76561197960287930"}})
    with patch("steam_api.requests.get", return_value=fake) as mock_get:
        steam_id = client.resolve_steam_id("gabelogannewell")
    assert steam_id == "76561197960287930"
    assert mock_get.call_args.kwargs["params"]["vanityurl"] == "gabelogannewell"


def test_resolve_steam_id_with_profile_url(client):
    fake = FakeResponse(200, {"response": {"success": 1, "steamid": "76561197960287930"}})
    with patch("steam_api.requests.get", return_value=fake):
        steam_id = client.resolve_steam_id("https://steamcommunity.com/id/gabelogannewell/")
    assert steam_id == "76561197960287930"


def test_resolve_steam_id_failure_raises(client):
    fake = FakeResponse(200, {"response": {"success": 42}})
    with patch("steam_api.requests.get", return_value=fake):
        with pytest.raises(SteamAPIError):
            client.resolve_steam_id("does-not-exist")


def test_get_player_summary_success(client):
    fake = FakeResponse(200, {"response": {"players": [{"steamid": "123", "personaname": "Rabscuttle"}]}})
    with patch("steam_api.requests.get", return_value=fake):
        profile = client.get_player_summary("123")
    assert profile["personaname"] == "Rabscuttle"


def test_get_player_summary_not_found_raises(client):
    fake = FakeResponse(200, {"response": {"players": []}})
    with patch("steam_api.requests.get", return_value=fake):
        with pytest.raises(SteamAPIError):
            client.get_player_summary("123")


def test_get_friend_list_private_returns_empty(client):
    fake = FakeResponse(500, {})
    with patch("steam_api.requests.get", return_value=fake):
        assert client.get_friend_list("123") == []


def test_get_player_bans(client):
    fake = FakeResponse(200, {"players": [{"SteamId": "123", "NumberOfVACBans": 1}]})
    with patch("steam_api.requests.get", return_value=fake):
        bans = client.get_player_bans("123")
    assert bans["NumberOfVACBans"] == 1


def test_get_owned_games_private_raises(client):
    fake = FakeResponse(200, {"response": {}})
    with patch("steam_api.requests.get", return_value=fake):
        with pytest.raises(SteamAPIError):
            client.get_owned_games("123")


def test_get_owned_games_success(client):
    fake = FakeResponse(200, {"response": {"games": [{"name": "Half-Life", "playtime_forever": 120}]}})
    with patch("steam_api.requests.get", return_value=fake):
        games = client.get_owned_games("123")
    assert games[0]["name"] == "Half-Life"


def test_get_inventory_item_counts_private_raises_403(client):
    fake = FakeResponse(403)
    with patch("steam_api.requests.get", return_value=fake):
        with pytest.raises(SteamAPIError, match="private"):
            client.get_inventory_item_counts("123")


def test_get_inventory_item_counts_empty_raises_400(client):
    fake = FakeResponse(400)
    with patch("steam_api.requests.get", return_value=fake):
        with pytest.raises(SteamAPIError):
            client.get_inventory_item_counts("123")


def test_get_inventory_item_counts_counts_items(client):
    fake = FakeResponse(200, {
        "assets": [
            {"classid": "1", "amount": "1"},
            {"classid": "1", "amount": "1"},
            {"classid": "2", "amount": "3"},
        ],
        "descriptions": [
            {"classid": "1", "market_hash_name": "Item A"},
            {"classid": "2", "market_hash_name": "Item B"},
        ],
        "more_items": 0,
    })
    with patch("steam_api.requests.get", return_value=fake):
        counts = client.get_inventory_item_counts("123")
    assert counts == {"Item A": 2, "Item B": 3}


def test_get_inventory_item_counts_paginates(client):
    page1 = FakeResponse(200, {
        "assets": [{"classid": "1", "amount": "1"}],
        "descriptions": [{"classid": "1", "market_hash_name": "Item A"}],
        "more_items": 1,
        "last_assetid": "999",
    })
    page2 = FakeResponse(200, {
        "assets": [{"classid": "1", "amount": "1"}],
        "descriptions": [{"classid": "1", "market_hash_name": "Item A"}],
        "more_items": 0,
    })
    with patch("steam_api.requests.get", side_effect=[page1, page2]), patch("steam_api.time.sleep"):
        counts = client.get_inventory_item_counts("123")
    assert counts == {"Item A": 2}


def test_get_market_price_parses_lowest_price(client):
    fake = FakeResponse(200, {"success": True, "lowest_price": "$1,234.56"})
    with patch("steam_api.requests.get", return_value=fake):
        price = client.get_market_price("Some Item")
    assert price == 1234.56


def test_get_market_price_returns_none_on_failure(client):
    fake = FakeResponse(200, {"success": False})
    with patch("steam_api.requests.get", return_value=fake):
        assert client.get_market_price("Some Item") is None


def test_get_player_achievements_private_raises_403(client):
    fake = FakeResponse(403)
    with patch("steam_api.requests.get", return_value=fake):
        with pytest.raises(SteamAPIError, match="private"):
            client.get_player_achievements("123", 730)


def test_get_player_achievements_success(client):
    fake = FakeResponse(200, {"playerstats": {"success": True, "achievements": [
        {"apiname": "ACH_1", "achieved": 1, "unlocktime": 1700000000},
        {"apiname": "ACH_2", "achieved": 0, "unlocktime": 0},
    ]}})
    with patch("steam_api.requests.get", return_value=fake):
        achievements = client.get_player_achievements("123", 730)
    assert len(achievements) == 2
    assert achievements[0]["achieved"] == 1


def test_get_player_achievements_failure_raises(client):
    fake = FakeResponse(200, {"playerstats": {"success": False, "error": "Requested app has no stats"}})
    with patch("steam_api.requests.get", return_value=fake):
        with pytest.raises(SteamAPIError, match="no stats"):
            client.get_player_achievements("123", 730)


def test_get_game_schema_achievements(client):
    fake = FakeResponse(200, {"game": {"availableGameStats": {"achievements": [
        {"name": "ACH_1", "displayName": "First Blood", "description": "Win a match"},
    ]}}})
    with patch("steam_api.requests.get", return_value=fake):
        schema = client.get_game_schema_achievements(730)
    assert schema["ACH_1"]["displayName"] == "First Blood"


def test_get_inventory_value_sums_priced_items(client):
    # Sorted by count descending, so "Item B" (3) is priced before "Item A" (2).
    item_counts = {"Item A": 2, "Item B": 3}
    with patch.object(client, "get_market_price", side_effect=[10.0, 5.0]), patch("steam_api.time.sleep"):
        total, priced = client.get_inventory_value(item_counts)
    assert total == 3 * 10.0 + 2 * 5.0
    assert priced == 2
