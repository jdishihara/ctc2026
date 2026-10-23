"""Map exchange symbols to Mario Markets contract roles.

A role is a tuple: ("race", r, racer) for the race-winner contract of race r (1-8), ("swin", s, racer) for the series-
winner contract of series s (1-2), ("s1", s) / ("s2", s) / ("top2", s) for the score contracts. Racer is the character
name (DAISY, PEACH, BIRDO, YOSHI).

The real symbol names are unknown until the day. `guess_role` parses the symbol, its name, group and market name;
`mario/contracts.json` (optional, {"SYMBOL": ["race", 1, "DAISY"], ...}) overrides the guess. The desk prints every
symbol it could not map and the `map` command prints the whole mapping: check it before the first race.
"""
from __future__ import annotations
import json, re
from pathlib import Path

RACERS = ["BIRDO", "DAISY", "PEACH", "YOSHI"]          # alphabetical: the pricer's humans A B C D
POINTS = [15, 12, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
LIMITS = {"race": 100, "swin": 200, "s1": 1000, "s2": 1000, "top2": 1000}
OVERRIDE = Path(__file__).resolve().parent / "contracts.json"


def _num(text: str, *keys: str) -> int | None:
    for k in keys:
        m = re.search(rf"\b{k}\s*[-_ ]?\s*(\d)\b", text)
        if m:
            return int(m.group(1))
    return None


def guess_role(sym: dict) -> tuple | None:
    """Best guess of the role of one symbol record ({"symbol", "name", "group", "market_name", ...})."""
    text = " ".join(str(sym.get(k) or "") for k in ("symbol", "name", "group", "market_name", "message")).upper()
    text = text.replace("_", " ").replace("-", " ")
    racer = next((r for r in RACERS if r in text), None)
    series = _num(text, "SERIES", "SER", "S")
    race = _num(text, "RACE", "RC", "R")
    # score contracts first. Packet names: "#1 Score", "#2 Score", "Top-2 Total"; a bare "TOP2" is read as the total
    is_s1 = re.search(r"#\s*1|NO\.?\s*1|NUM\s*1|SCORE\s*1|1ST|FIRST|HIGHEST|TOP\s*1\b", text)
    is_s2 = re.search(r"#\s*2|NO\.?\s*2|NUM\s*2|SCORE\s*2|2ND|SECOND", text)
    is_top2 = re.search(r"TOP\s*[- ]?\s*2|TOP\s*TWO|TOTAL|SUM", text)
    if series and not racer and "WIN" not in text:
        if is_s1 and not is_top2:
            return ("s1", series)
        if is_s2 and not is_top2:
            return ("s2", series)
        if is_top2:
            return ("top2", series)
    if racer and race:                     # a race number wins over a series label (symbols often carry both)
        return ("race", race, racer)
    if racer and series:
        return ("swin", series, racer)
    return None


def load_roles(symbols: list[dict]) -> tuple[dict[str, tuple], list[str]]:
    """Roles for every symbol (override file first, then the guess) and the list of unmapped symbols."""
    override = {}
    if OVERRIDE.exists():
        override = {k: tuple(v) for k, v in json.loads(OVERRIDE.read_text()).items()}
    roles, unmapped = {}, []
    for s in symbols:
        name = s["symbol"]
        role = override.get(name) or guess_role(s)
        if role is None:
            unmapped.append(name)
        else:
            roles[name] = role
    return roles, unmapped


def role_label(role: tuple) -> str:
    if role[0] == "race":
        return f"R{role[1]} win {role[2].title()}"
    if role[0] == "swin":
        return f"S{role[1]} win {role[2].title()}"
    return {"s1": "#1 score", "s2": "#2 score", "top2": "top-2 total"}[role[0]] + f" S{role[1]}"


def series_of(role: tuple) -> int:
    return (role[1] - 1) // 4 + 1 if role[0] == "race" else role[1]
