"""Deterministic themed user avatars."""
from urllib.parse import quote

AVATAR_COLORS = ("#2563eb", "#059669", "#d97706", "#db2777", "#7c3aed", "#0891b2", "#dc2626")
AVATAR_THEMES = ("plain", "christmas", "halloween", "heart", "star", "crown", "coffee")


def avatar_color_for_user(user_id: int) -> str:
    return AVATAR_COLORS[(int(user_id) - 1) % len(AVATAR_COLORS)]


def build_avatar_url(color: str, theme: str = "plain") -> str:
    theme = theme if theme in AVATAR_THEMES else "plain"
    decoration = {
        "christmas": '<path d="M28 29L50 8l22 21Z" fill="#dc2626"/><circle cx="50" cy="8" r="5" fill="#fff"/>',
        "halloween": '<path d="M22 29h56L66 10H34Z" fill="#f97316"/><circle cx="42" cy="45" r="3"/><circle cx="58" cy="45" r="3"/>',
        "heart": '<path d="M50 78S18 58 18 38c0-13 17-18 32-3 15-15 32-10 32 3 0 20-32 40-32 40Z" fill="#ef4444"/>',
        "star": '<path d="m50 14 7 20 21 1-16 13 5 21-17-11-17 11 5-21-16-13 21-1Z" fill="#facc15"/>',
        "crown": '<path d="m23 31 7-18 20 13 20-13 7 18Z" fill="#facc15"/><path d="M25 31h50v9H25Z" fill="#eab308"/>',
        "coffee": '<path d="M30 38h35v24a8 8 0 0 1-8 8H38a8 8 0 0 1-8-8Z" fill="#fff"/><path d="M65 44h7a8 8 0 0 1 0 16h-7" fill="none" stroke="#fff" stroke-width="5"/>',
    }.get(theme, "")
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <rect width="100" height="100" rx="24" fill="{color}"/>
      <circle cx="50" cy="52" r="25" fill="#fff" opacity=".92"/>
      <circle cx="41" cy="49" r="3" fill="#172033"/><circle cx="59" cy="49" r="3" fill="#172033"/>
      <path d="M40 62q10 8 20 0" fill="none" stroke="#172033" stroke-width="3" stroke-linecap="round"/>
      {decoration}
    </svg>'''
    # Keep whitespace between SVG tag/attribute names. Removing all whitespace
    # turns `svg xmlns` into the invalid element name `svgxmlns`.
    return "data:image/svg+xml;charset=utf-8," + quote(svg.strip())
