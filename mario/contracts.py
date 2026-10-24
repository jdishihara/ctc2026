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


def _classify(text: str, symbol_only: bool) -> tuple | None:
    """One pass over an upper-cased, de-punctuated text. symbol_only enables the terse rules (S1_1, S1_P2, S1_T2) that are
    only safe when the text is the bare symbol, not the symbol joined with its name and group."""
    racer = next((r for r in RACERS if r in text), None)
    series = _num(text, "SERIES", "SER", "SWIN", "S")
    race = _num(text, "RACE", "RC", "R")
    # score contracts first. Packet names: "#1 Score", "#2 Score", "Top-2 Total"; a bare "TOP2" is read as the total
    is_top2 = re.search(r"TOP\s*[- ]?\s*2|TOP\s*TWO|TOTAL|SUM|\bT\s*2\b", text)
    is_s2 = re.search(r"#\s*2|NO\.?\s*2|NUM\s*2|SCORE\s*2|2ND|SECOND|RUNNER|\bP\s*2\b", text)
    is_s1 = re.search(r"#\s*1|NO\.?\s*1|NUM\s*1|SCORE\s*1|1ST|FIRST|HIGHEST|TOP\s*1\b|\bP\s*1\b|\bTOP$|\bLEADER", text)
    if symbol_only and series and not racer:
        if re.search(r"\s1$", text) and not is_top2:
            is_s1 = is_s1 or True
        if re.search(r"\s2$", text) and not is_top2:
            is_s2 = is_s2 or True
    if series and not racer and "WIN" not in text:
        if is_top2:
            return ("top2", series)
        if is_s2:
            return ("s2", series)
        if is_s1:
            return ("s1", series)
    if racer and race:                     # a race number wins over a series label (symbols often carry both)
        return ("race", race, racer)
    if racer and series:
        return ("swin", series, racer)
    return None


def guess_role(sym: dict) -> tuple | None:
    """Best guess of the role of one symbol record ({"symbol", "name", "group", "market_name", ...}): the bare symbol
    first (terse exchange codes), then the symbol joined with its descriptive fields."""
    clean = lambda t: t.upper().replace("_", " ").replace("-", " ")
    role = _classify(clean(str(sym.get("symbol") or "")), symbol_only=True)
    if role is not None:
        return role
    text = clean(" ".join(str(sym.get(k) or "") for k in ("symbol", "name", "group", "market_name", "message")))
    return _classify(text, symbol_only=False)


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


def parse_race(tokens: list[str]) -> list[int]:
    """The humans' overall places from a typed `race ...` line. Either four integers in BIRDO DAISY PEACH YOSHI order
    (`race 1 2 5 9`) or racer names with their places in any order (`race peach 5 birdo 1 yoshi 9 daisy 2`,
    `race daisy=2 birdo=1 ...`); names may be abbreviated to their first three letters. Raises ValueError with a message
    the dashboard can show."""
    toks = [t for tok in tokens for t in tok.replace("=", " ").replace(":", " ").replace(",", " ").split() if t]
    if len(toks) == 4 and all(t.isdigit() for t in toks):
        places = [int(t) for t in toks]
    else:
        by_name: dict[str, int] = {}
        pending_name = None
        pending_num = None
        for t in toks:
            if t.isdigit():
                if pending_name is not None:
                    by_name[pending_name] = int(t); pending_name = None
                else:
                    pending_num = int(t)
                continue
            name = next((r for r in RACERS if r.startswith(t.upper()[:3])), None)
            if name is None:
                raise ValueError(f"'{t}' is not a racer (Birdo, Daisy, Peach, Yoshi) or a place")
            if pending_num is not None:
                by_name[name] = pending_num; pending_num = None
            else:
                pending_name = name
        missing = [r.title() for r in RACERS if r not in by_name]
        if missing or pending_name is not None or pending_num is not None:
            raise ValueError("need a place for every racer; missing " + ", ".join(missing) if missing else "unpaired token")
        places = [by_name[r] for r in RACERS]
    if len(places) != 4 or len(set(places)) != 4 or not all(1 <= p <= 12 for p in places):
        raise ValueError("need 4 distinct overall places 1..12 (12 racers: 4 humans + 8 CPUs)")
    return places


def role_label(role: tuple) -> str:
    if role[0] == "race":
        return f"R{role[1]} win {role[2].title()}"
    if role[0] == "swin":
        return f"S{role[1]} win {role[2].title()}"
    return {"s1": "#1 score", "s2": "#2 score", "top2": "top-2 total"}[role[0]] + f" S{role[1]}"


def series_of(role: tuple) -> int:
    return (role[1] - 1) // 4 + 1 if role[0] == "race" else role[1]
