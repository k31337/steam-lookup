from main import compute_trust_score


def clean_profile():
    return {"communityvisibilitystate": 3}


def clean_bans():
    return {"NumberOfVACBans": 0, "NumberOfGameBans": 0, "CommunityBanned": False, "EconomyBan": "none"}


def test_clean_old_public_profile_scores_100():
    score, reasons = compute_trust_score(
        clean_profile(), clean_bans(), account_age_days=3650,
        games_private=False, inventory_private=False, friends_private=False,
    )
    assert score == 100
    assert reasons == ["No red flags detected"]


def test_vac_ban_lowers_score_and_is_reported():
    bans = clean_bans()
    bans["NumberOfVACBans"] = 1
    score, reasons = compute_trust_score(
        clean_profile(), bans, account_age_days=3650,
        games_private=False, inventory_private=False, friends_private=False,
    )
    assert score == 60
    assert "Has VAC ban(s)" in reasons


def test_new_account_is_penalized():
    score, reasons = compute_trust_score(
        clean_profile(), clean_bans(), account_age_days=5,
        games_private=False, inventory_private=False, friends_private=False,
    )
    assert score == 75
    assert "Account younger than 30 days" in reasons


def test_private_profile_is_penalized():
    profile = {"communityvisibilitystate": 1}
    score, reasons = compute_trust_score(
        profile, clean_bans(), account_age_days=3650,
        games_private=False, inventory_private=False, friends_private=False,
    )
    assert score == 80
    assert "Profile is private" in reasons


def test_fully_hidden_profile_is_penalized():
    score, reasons = compute_trust_score(
        clean_profile(), clean_bans(), account_age_days=3650,
        games_private=True, inventory_private=True, friends_private=True,
    )
    assert score == 85
    assert "Games, inventory, and friends are all hidden" in reasons


def test_score_never_goes_below_zero():
    bans = {"NumberOfVACBans": 5, "NumberOfGameBans": 5, "CommunityBanned": True, "EconomyBan": "banned"}
    profile = {"communityvisibilitystate": 1}
    score, _ = compute_trust_score(
        profile, bans, account_age_days=1,
        games_private=True, inventory_private=True, friends_private=True,
    )
    assert score == 0
