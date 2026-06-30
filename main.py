"""Shows information for a Steam profile: basic info, friends, and bans."""
import json
import os
import sys
import unicodedata
from datetime import datetime, timezone

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
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


def sanitize_display_name(name: str) -> str:
    """Strips zero-width and combining-mark characters that break table column
    alignment on terminals/fonts that render them with non-zero width anyway."""
    return "".join(ch for ch in name if unicodedata.category(ch) not in ("Mn", "Me", "Cf")) or "Unknown"


def compute_trust_score(
    profile: dict, bans: dict, account_age_days: float | None,
    games_private: bool, inventory_private: bool, friends_private: bool,
) -> tuple[int, list[str]]:
    """Returns a rough, non-official 0-100 trust score and the reasons behind it.

    This is a simple heuristic for quick orientation only — it is not provided
    or endorsed by Valve and should never be the sole basis for trust decisions.
    """
    score = 100
    reasons = []

    if bans.get("NumberOfVACBans", 0) > 0:
        score -= 40
        reasons.append("Has VAC ban(s)")
    if bans.get("NumberOfGameBans", 0) > 0:
        score -= 25
        reasons.append("Has game ban(s)")
    if bans.get("CommunityBanned"):
        score -= 15
        reasons.append("Community banned")
    if bans.get("EconomyBan", "none") != "none":
        score -= 10
        reasons.append("Economy ban active")

    if account_age_days is None:
        score -= 10
        reasons.append("Account creation date unavailable")
    elif account_age_days < 30:
        score -= 25
        reasons.append("Account younger than 30 days")
    elif account_age_days < 365:
        score -= 10
        reasons.append("Account younger than 1 year")

    if profile.get("communityvisibilitystate") != 3:
        score -= 20
        reasons.append("Profile is private")

    if games_private and inventory_private and friends_private:
        score -= 15
        reasons.append("Games, inventory, and friends are all hidden")

    score = max(0, min(100, score))
    if not reasons:
        reasons.append("No red flags detected")
    return score, reasons


def print_profile(client: SteamClient, steam_id: str) -> dict:
    data: dict = {}

    profile = client.get_player_summary(steam_id)
    data["profile"] = profile
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
    data["steam_level"] = level
    data["badges"] = badges
    badge_lines = [f"[bold]Steam level:[/bold] {level}", f"[bold]Total badges:[/bold] {len(badges)}"]
    for badge in sorted(badges, key=lambda b: b.get("xp", 0), reverse=True)[:5]:
        appid = badge.get("appid")
        label = f"Game badge (AppID {appid})" if appid else f"Special badge #{badge.get('badgeid', '?')}"
        badge_lines.append(f"  - {label}: level {badge.get('level', 0)}, {badge.get('xp', 0)} XP")
    console.print(Panel("\n".join(badge_lines), title="Level & Badges", border_style="yellow"))

    games_private = False
    try:
        games = client.get_owned_games(steam_id)
    except SteamAPIError as e:
        games_private = True
        data["games"] = None
        console.print(Panel(str(e), title="Games", border_style="grey50"))
    else:
        total_hours = sum(g.get("playtime_forever", 0) for g in games) / 60
        data["games"] = {"count": len(games), "total_hours": round(total_hours, 1), "games": games}
        game_lines = [f"[bold]Owned games:[/bold] {len(games)}", f"[bold]Total playtime:[/bold] {total_hours:,.1f} hours"]
        top_games = sorted(games, key=lambda g: g.get("playtime_forever", 0), reverse=True)[:5]
        for g in top_games:
            hours = g.get("playtime_forever", 0) / 60
            game_lines.append(f"  - {g.get('name', 'Unknown')}: {hours:,.1f} hours")
        console.print(Panel("\n".join(game_lines), title="Games", border_style="green"))

    bans = client.get_player_bans(steam_id)
    data["bans"] = bans
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

    inventory_private = False
    try:
        item_counts = client.get_inventory_item_counts(steam_id)
    except SteamAPIError as e:
        inventory_private = True
        data["cs2_inventory"] = None
        console.print(Panel(str(e), title="CS2 Inventory", border_style="grey50"))
    else:
        total_items = sum(item_counts.values())
        data["cs2_inventory"] = {
            "total_items": total_items, "unique_items": len(item_counts), "item_counts": item_counts,
        }
        inv_lines = [f"[bold]Total items:[/bold] {total_items}", f"[bold]Unique items:[/bold] {len(item_counts)}"]
        top_items = sorted(item_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
        for name, count in top_items:
            inv_lines.append(f"  - {name} x{count}")

        if item_counts:
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                console=console,
            ) as progress:
                task = progress.add_task("Fetching market prices...", total=None)

                def on_item_priced(index: int, total: int, name: str) -> None:
                    progress.update(task, completed=index, total=total)

                total_value, priced_count = client.get_inventory_value(
                    item_counts, on_item_priced=on_item_priced
                )
            data["cs2_inventory"]["estimated_value_usd"] = round(total_value, 2)
            data["cs2_inventory"]["priced_unique_items"] = priced_count
            inv_lines.append(f"\n[bold]Estimated value:[/bold] ~${total_value:,.2f} USD")
            inv_lines.append(
                f"[dim](based on lowest market price for the top {priced_count} most common unique items)[/dim]"
            )

        console.print(Panel("\n".join(inv_lines), title="CS2 Inventory", border_style="blue"))

    friends_private = False
    friends = client.get_friend_list(steam_id)
    if not friends:
        friends_private = True
        data["friends"] = None
        console.print(Panel(
            "Could not retrieve friend list (private profile or no friends).",
            title="Friends", border_style="grey50",
        ))
    else:
        friend_ids = [f["steamid"] for f in friends]
        names_by_id = {}
        bans_by_id = {}
        for batch_start in range(0, len(friend_ids), 100):
            batch = friend_ids[batch_start:batch_start + 100]
            for p in client.get_player_summaries(batch):
                names_by_id[p["steamid"]] = p.get("personaname", "Unknown")
            for b in client.get_players_bans(batch):
                bans_by_id[b["SteamId"]] = b

        friends_data = []
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
            friends_data.append({"steamid": fid, "name": name, "ban_status": status_text})

        data["friends"] = {"count": len(friends), "friends": friends_data}

        page_size = 25
        for page_start in range(0, len(friends_data), page_size):
            page = friends_data[page_start:page_start + page_size]
            page_end = page_start + len(page)
            table = Table(
                title=f"Friends {page_start + 1}-{page_end} of {len(friends_data)}",
                border_style="magenta", expand=False,
            )
            table.add_column("Name", style="bold", max_width=30, overflow="ellipsis", no_wrap=True)
            table.add_column("SteamID64", no_wrap=True)
            table.add_column("Ban status", no_wrap=True)
            for entry in page:
                status_style = "green" if entry["ban_status"] == "clean" else "red"
                table.add_row(
                    sanitize_display_name(entry["name"]), entry["steamid"],
                    f"[{status_style}]{entry['ban_status']}[/{status_style}]",
                )
            console.print(table)

    account_age_days = None
    if "timecreated" in profile:
        account_age_days = (datetime.now(timezone.utc) - datetime.fromtimestamp(
            profile["timecreated"], tz=timezone.utc
        )).days
    score, reasons = compute_trust_score(
        profile, bans, account_age_days, games_private, inventory_private, friends_private
    )
    if score >= 75:
        score_color = "green"
    elif score >= 45:
        score_color = "yellow"
    else:
        score_color = "red"
    trust_lines = [f"[bold {score_color}]Score: {score}/100[/bold {score_color}]"]
    trust_lines += [f"  - {reason}" for reason in reasons]
    trust_lines.append("\n[dim]Unofficial heuristic for quick orientation only — not a Valve-provided signal.[/dim]")
    console.print(Panel("\n".join(trust_lines), title="Trust Assessment", border_style=score_color))
    data["trust_assessment"] = {"score": score, "reasons": reasons}

    return data


def print_common_friends(client: SteamClient, steam_id_a: str, steam_id_b: str) -> None:
    profile_a = client.get_player_summary(steam_id_a)
    profile_b = client.get_player_summary(steam_id_b)

    friends_a = {f["steamid"] for f in client.get_friend_list(steam_id_a)}
    friends_b = {f["steamid"] for f in client.get_friend_list(steam_id_b)}
    if not friends_a or not friends_b:
        console.print(Panel(
            "Could not compare friend lists (one or both profiles have a private friend list).",
            title="Common Friends", border_style="grey50",
        ))
        return

    common_ids = sorted(friends_a & friends_b)
    if not common_ids:
        console.print(Panel("No friends in common.", title="Common Friends", border_style="grey50"))
        return

    names_by_id = {}
    for batch_start in range(0, len(common_ids), 100):
        batch = common_ids[batch_start:batch_start + 100]
        for p in client.get_player_summaries(batch):
            names_by_id[p["steamid"]] = p.get("personaname", "Unknown")

    table = Table(
        title=f"Common Friends: {profile_a.get('personaname')} & {profile_b.get('personaname')} ({len(common_ids)})",
        border_style="magenta", expand=False,
    )
    table.add_column("Name", style="bold", max_width=30, overflow="ellipsis", no_wrap=True)
    table.add_column("SteamID64", no_wrap=True)
    for fid in common_ids:
        table.add_row(sanitize_display_name(names_by_id.get(fid, "Unknown")), fid)
    console.print(table)


def print_achievements(client: SteamClient, steam_id: str, app_id: int) -> None:
    achievements = client.get_player_achievements(steam_id, app_id)
    if not achievements:
        console.print(Panel(
            f"No achievements found for AppID {app_id}.",
            title="Achievements", border_style="grey50",
        ))
        return

    schema = client.get_game_schema_achievements(app_id)
    unlocked = [a for a in achievements if a.get("achieved")]
    locked = [a for a in achievements if not a.get("achieved")]
    pct = len(unlocked) / len(achievements) * 100

    table = Table(
        title=f"Achievements for AppID {app_id}: {len(unlocked)}/{len(achievements)} ({pct:.1f}%)",
        border_style="cyan", expand=False,
    )
    table.add_column("Achievement", style="bold", max_width=45, overflow="ellipsis", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Unlocked", no_wrap=True)

    ordered = sorted(unlocked, key=lambda a: a.get("unlocktime", 0), reverse=True) + locked
    for a in ordered:
        apiname = a.get("apiname", "?")
        display_name = sanitize_display_name(schema.get(apiname, {}).get("displayName", apiname))
        if a.get("achieved"):
            status, status_style = "Unlocked", "green"
            unlock_date = format_timestamp(a["unlocktime"]) if a.get("unlocktime") else "-"
        else:
            status, status_style, unlock_date = "Locked", "grey50", "-"
        table.add_row(display_name, f"[{status_style}]{status}[/{status_style}]", unlock_date)

    console.print(table)


def main() -> None:
    load_dotenv()
    args = sys.argv[1:]
    if not args:
        console.print(
            "Usage: python main.py <steamid64 | vanity_url | profile_url> "
            "[--compare <other_identifier>] [--export <output.json>] [--achievements <appid>]"
        )
        sys.exit(1)

    api_key = os.getenv("STEAM_API_KEY", "")
    identifier = args[0]

    compare_identifier = None
    if "--compare" in args:
        idx = args.index("--compare")
        if idx + 1 >= len(args):
            console.print("Usage: python main.py <identifier> --compare <other_identifier>")
            sys.exit(1)
        compare_identifier = args[idx + 1]

    export_path = None
    if "--export" in args:
        idx = args.index("--export")
        if idx + 1 >= len(args):
            console.print("Usage: python main.py <identifier> --export <output.json>")
            sys.exit(1)
        export_path = args[idx + 1]

    achievements_appid = None
    if "--achievements" in args:
        idx = args.index("--achievements")
        if idx + 1 >= len(args):
            console.print("Usage: python main.py <identifier> --achievements <appid>")
            sys.exit(1)
        try:
            achievements_appid = int(args[idx + 1])
        except ValueError:
            console.print(f"[bold red]Error:[/bold red] --achievements requires a numeric AppID, got '{args[idx + 1]}'")
            sys.exit(1)

    try:
        client = SteamClient(api_key)
        steam_id = client.resolve_steam_id(identifier)
        if compare_identifier:
            other_steam_id = client.resolve_steam_id(compare_identifier)
            print_common_friends(client, steam_id, other_steam_id)
            if export_path:
                console.print("[yellow]Note:[/yellow] --export is not supported with --compare.")
        elif achievements_appid:
            print_achievements(client, steam_id, achievements_appid)
        else:
            data = print_profile(client, steam_id)
            if export_path:
                with open(export_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                console.print(f"\n[bold green]Exported results to {export_path}[/bold green]")
    except SteamAPIError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
