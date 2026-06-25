"""Shows information for a Steam profile: basic info, friends, and bans."""
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from steam_api import SteamClient, SteamAPIError

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

console = Console()

PERSONA_STATES = {
    0: "Offline", 1: "Online", 2: "Busy", 3: "Away",
    4: "Snooze", 5: "Looking to trade", 6: "Looking to play",
}


def format_timestamp(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def print_profile(client: SteamClient, steam_id: str) -> None:
    profile = client.get_player_summary(steam_id)
    status = PERSONA_STATES.get(profile.get("personastate"), "Unknown")
    status_color = "green" if status == "Online" else "white"

    info_lines = [
        f"[bold]Name:[/bold] {profile.get('personaname')}",
        f"[bold]SteamID64:[/bold] {profile.get('steamid')}",
        f"[bold]Profile URL:[/bold] {profile.get('profileurl')}",
        f"[bold]Status:[/bold] [{status_color}]{status}[/{status_color}]",
    ]
    if "timecreated" in profile:
        info_lines.append(f"[bold]Account created:[/bold] {format_timestamp(profile['timecreated'])}")
    if "loccountrycode" in profile:
        info_lines.append(f"[bold]Country:[/bold] {profile['loccountrycode']}")
    console.print(Panel("\n".join(info_lines), title="Profile", border_style="cyan"))

    level = client.get_steam_level(steam_id)
    badges = client.get_badges(steam_id)
    badge_lines = [f"[bold]Steam level:[/bold] {level}", f"[bold]Total badges:[/bold] {len(badges)}"]
    for badge in sorted(badges, key=lambda b: b.get("level", 0), reverse=True)[:5]:
        badge_lines.append(
            f"  - Badge {badge.get('badgeid', '?')} (level {badge.get('level', 0)}, {badge.get('xp', 0)} XP)"
        )
    console.print(Panel("\n".join(badge_lines), title="Level & Badges", border_style="yellow"))

    bans = client.get_player_bans(steam_id)
    has_bans = bans.get("NumberOfVACBans", 0) > 0 or bans.get("NumberOfGameBans", 0) > 0 or bans.get("CommunityBanned")
    ban_color = "red" if has_bans else "green"
    ban_lines = [
        f"[bold]VAC bans:[/bold] {bans.get('NumberOfVACBans', 0)}",
        f"[bold]Game bans:[/bold] {bans.get('NumberOfGameBans', 0)}",
        f"[bold]Community ban:[/bold] {'Yes' if bans.get('CommunityBanned') else 'No'}",
        f"[bold]Economy ban:[/bold] {bans.get('EconomyBan', 'none')}",
    ]
    if bans.get("DaysSinceLastBan", 0) > 0:
        ban_lines.append(f"[bold]Days since last ban:[/bold] {bans['DaysSinceLastBan']}")
    console.print(Panel("\n".join(ban_lines), title="Bans", border_style=ban_color))

    try:
        item_counts = client.get_inventory_item_counts(steam_id)
    except SteamAPIError as e:
        console.print(Panel(str(e), title="CS2 Inventory", border_style="grey50"))
    else:
        total_items = sum(item_counts.values())
        inv_lines = [f"[bold]Total items:[/bold] {total_items}", f"[bold]Unique items:[/bold] {len(item_counts)}"]
        top_items = sorted(item_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
        for name, count in top_items:
            inv_lines.append(f"  - {name} x{count}")

        if item_counts:
            with console.status("Fetching market prices..."):
                total_value, priced_count = client.get_inventory_value(item_counts)
            inv_lines.append(f"\n[bold]Estimated value:[/bold] ~${total_value:,.2f} USD")
            inv_lines.append(
                f"[dim](based on lowest market price for the top {priced_count} most common unique items)[/dim]"
            )

        console.print(Panel("\n".join(inv_lines), title="CS2 Inventory", border_style="blue"))

    friends = client.get_friend_list(steam_id)
    if not friends:
        console.print(Panel(
            "Could not retrieve friend list (private profile or no friends).",
            title="Friends", border_style="grey50",
        ))
        return

    friend_ids = [f["steamid"] for f in friends]
    names_by_id = {}
    bans_by_id = {}
    for batch_start in range(0, len(friend_ids), 100):
        batch = friend_ids[batch_start:batch_start + 100]
        for p in client.get_player_summaries(batch):
            names_by_id[p["steamid"]] = p.get("personaname", "Unknown")
        for b in client.get_players_bans(batch):
            bans_by_id[b["SteamId"]] = b

    table = Table(title=f"Friends ({len(friends)})", border_style="magenta")
    table.add_column("Name", style="bold")
    table.add_column("SteamID64")
    table.add_column("Ban status")

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
        status_text = ", ".join(flags) if flags else "clean"
        status_style = "red" if flags else "green"
        table.add_row(name, fid, f"[{status_style}]{status_text}[/{status_style}]")

    console.print(table)


def main() -> None:
    load_dotenv()
    if len(sys.argv) < 2:
        console.print("Usage: python main.py <steamid64 | vanity_url | profile_url>")
        sys.exit(1)

    api_key = os.getenv("STEAM_API_KEY")
    identifier = sys.argv[1]

    try:
        client = SteamClient(api_key)
        steam_id = client.resolve_steam_id(identifier)
        print_profile(client, steam_id)
    except SteamAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
