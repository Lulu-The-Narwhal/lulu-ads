"""Client-adaptive plain-text formatting for CLI hosts.

Rich chat UIs (Claude.ai, Claude Desktop) can render the MCP Apps widget —
an actual card, regardless of what the model says in words. A terminal has
no such surface: the model's own text is the only output there is. This
module formats the disclosed sponsored line as a bordered plain-text block
instead of a plain sentence, so it reads as a distinct "card" even in a
bare terminal — still just `content[].text`, still zero instruction to the
model about what to say. Text formatting, not a directive.

Detection is based on the MCP `clientInfo.name` sent by the client at
`initialize` — confirmed real values only, not guessed. Extend
KNOWN_CLI_CLIENTS as more are verified; unknown clients get no card (the
plain field only), never a false positive that mis-formats a rich UI.
"""

KNOWN_CLI_CLIENTS: frozenset[str] = frozenset({
    "claude-code",  # confirmed live: clientInfo.name == "claude-code" (v2.1.212)
})

_CARD_WIDTH = 46


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width:
            if current:
                lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def is_cli_client(client_name: str | None) -> bool:
    return bool(client_name) and client_name in KNOWN_CLI_CLIENTS


_FOOTER = "via Lulu Ads"


def format_cli_card(sponsored: dict, width: int = _CARD_WIDTH) -> str:
    """Renders sponsored as a bordered plain-text block using box-drawing
    characters — works in any terminal, no special renderer needed. Rounded
    corners and a "via Lulu Ads" footer keep it recognizable as our card
    specifically, not just a generic box some other tool printed.

    Only ANSI-free Unicode box-drawing characters -- a live test confirmed
    Claude Code strips raw ANSI escape bytes from tool output before the
    model ever sees them (the model gets the literal text "[38;5;208m",
    not a color), so color escapes would render as garbage, not color.

    The tracking URL (a JWT-signed https://ads.getlulu.dev/c/<token> link)
    can run past 200 characters — forcing it inside the box blows the
    border out to match, which looks absurd, not like a card. The link
    stays fully intact and clickable, just printed on its own line below
    the box instead of forced into the fixed-width border.
    """
    label = str(sponsored.get("label", "Sponsored"))
    text = str(sponsored.get("text", ""))
    url = str(sponsored.get("url", ""))

    body_lines = _wrap(text, width)
    inner_width = max(len(label) + 2, len(_FOOTER) + 2, *(len(line) for line in body_lines), width)

    top = "╭─ " + label + " " + "─" * (inner_width - len(label) - 1) + "╮"
    bottom = "╰─ " + _FOOTER + " " + "─" * (inner_width - len(_FOOTER) - 1) + "╯"
    body = "\n".join(f"│ {line.ljust(inner_width)} │" for line in body_lines)

    lines = [top, body, bottom]
    if url:
        lines.append(f"→ {url}")
    return "\n".join(lines)
