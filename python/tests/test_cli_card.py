from lulu_ads.cli_card import format_cli_card, is_cli_client


def test_is_cli_client_matches_known_names_only():
    assert is_cli_client("claude-code") is True
    assert is_cli_client("claude-ai") is False
    assert is_cli_client(None) is False
    assert is_cli_client("") is False


def test_format_cli_card_has_rounded_border_and_footer():
    card = format_cli_card({"label": "Sponsored", "text": "Save 15% at checkout", "url": "https://x.co/1"})
    lines = card.splitlines()
    assert lines[0].startswith("╭─ Sponsored")
    assert lines[0].endswith("╮")
    assert lines[-2].startswith("╰─ via Lulu Ads")
    assert lines[-2].endswith("╯")
    assert lines[-1] == "→ https://x.co/1"
    # every body/border line lines up to the same width
    widths = {len(line) for line in lines[:-1]}
    assert len(widths) == 1


def test_format_cli_card_long_url_stays_outside_the_box():
    long_url = "https://ads.getlulu.dev/c/" + "a" * 200
    card = format_cli_card({"label": "Sponsored", "text": "short", "url": long_url})
    lines = card.splitlines()
    assert lines[-1] == f"→ {long_url}"
    # box width unaffected by URL length
    assert max(len(line) for line in lines[:-1]) < 80


def test_format_cli_card_no_url_omits_link_line():
    card = format_cli_card({"label": "Sponsored", "text": "hi", "url": ""})
    assert "→" not in card
