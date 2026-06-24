"""Shows information for a Steam profile: basic info, friends, and bans."""
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from steam_api import SteamClient, SteamAPIError

PERSONA_STATES = {
    0: "Offline", 1: "Online", 2: "Busy", 3: "Away",
    4: "Snooze", 5: "Looking to trade", 6: "Looking to play",
}


def format_timestamp(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def print_profile(client: SteamClient, steam_id: str) -> None:
    profile = client.get_player_summary(steam_id)
    print("\n== Profile ==")
    print(f"Name: {profile.get('personaname')}")
    print(f"SteamID64: {profile.get('steamid')}")
    print(f"Profile URL: {profile.get('profileurl')}")
    print(f"Status: {PERSONA_STATES.get(profile.get('personastate'), 'Unknown')}")
    if "timecreated" in profile:
        print(f"Account created: {format_timestamp(profile['timecreated'])}")
    if "loccountrycode" in profile:
        print(f"Country: {profile['loccountrycode']}")

    print("\n== Bans ==")
    bans = client.get_player_bans(steam_id)
    print(f"VAC bans: {bans.get('NumberOfVACBans', 0)}")
    print(f"Game bans: {bans.get('NumberOfGameBans', 0)}")
    print(f"Community ban: {'Yes' if bans.get('CommunityBanned') else 'No'}")
    print(f"Economy ban: {bans.get('EconomyBan', 'none')}")
    if bans.get("DaysSinceLastBan", 0) > 0:
        print(f"Days since last ban: {bans['DaysSinceLastBan']}")

    print("\n== Friends ==")
    friends = client.get_friend_list(steam_id)
    if not friends:
        print("Could not retrieve friend list (private profile or no friends).")
        return
    print(f"Total friends: {len(friends)}")
    friend_ids = [f["steamid"] for f in friends]
    names_by_id = {}
    bans_by_id = {}
    for batch_start in range(0, len(friend_ids), 100):
        batch = friend_ids[batch_start:batch_start + 100]
        for p in client.get_player_summaries(batch):
            names_by_id[p["steamid"]] = p.get("personaname", "Unknown")
        for b in client.get_players_bans(batch):
            bans_by_id[b["SteamId"]] = b

    for fid in friend_ids:
        name = names_by_id.get(fid, "Unknown")
        ban = bans_by_id.get(fid, {})
        flags = []
        if ban.get("NumberOfVACBans", 0) > 0:
            flags.append(f"VAC x{ban['NumberOfVACBans']}")
        if ban.get("NumberOfGameBans", 0) > 0:
            flags.append(f"Game ban x{ban['NumberOfGameBans']}")
        if ban.get("CommunityBanned"):
            flags.append("Community ban")
        status = ", ".join(flags) if flags else "clean"
        print(f"  - {name} ({fid}): {status}")


def main() -> None:
    load_dotenv()
    if len(sys.argv) < 2:
        print("Usage: python main.py <steamid64 | vanity_url | profile_url>")
        sys.exit(1)

    api_key = os.getenv("STEAM_API_KEY")
    identifier = sys.argv[1]

    try:
        client = SteamClient(api_key)
        steam_id = client.resolve_steam_id(identifier)
        print_profile(client, steam_id)
    except SteamAPIError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
