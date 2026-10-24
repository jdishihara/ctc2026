"""Symbol -> role parsing for the Mario desk: the real symbol names are unknown until the day, so the parser must read
every plausible scheme (terse codes, verbose codes, racer-first codes, and descriptive names on an opaque code)."""
import pytest

from mario.contracts import guess_role

CODES = {
    "R1_BIRDO": ("race", 1, "BIRDO"), "S1_WIN_PEACH": ("swin", 1, "PEACH"), "S1_NO1": ("s1", 1), "S1_NO2": ("s2", 1), "S1_TOP2": ("top2", 1),
    "RACE1_WINNER_DAISY": ("race", 1, "DAISY"), "RACE_5_YOSHI": ("race", 5, "YOSHI"), "SERIES2_WINNER_BIRDO": ("swin", 2, "BIRDO"),
    "SERIES1_SCORE1": ("s1", 1), "SERIES1_SCORE2": ("s2", 1), "SERIES1_TOP2_TOTAL": ("top2", 1),
    "S2_1ST_SCORE": ("s1", 2), "S2_2ND_SCORE": ("s2", 2), "S2_TOP_TWO": ("top2", 2),
    "SER1_HIGHEST": ("s1", 1), "SER1_SECOND": ("s2", 1), "SER1_SUM": ("top2", 1),
    "PEACH_R3": ("race", 3, "PEACH"), "YOSHI_S2": ("swin", 2, "YOSHI"), "DAISY_RACE7": ("race", 7, "DAISY"), "BIRDO_SERIES1": ("swin", 1, "BIRDO"),
    "WIN_R2_DAISY": ("race", 2, "DAISY"), "SWIN2_PEACH": ("swin", 2, "PEACH"), "R8_YOSHI_WIN": ("race", 8, "YOSHI"), "MK_R4_BIRDO": ("race", 4, "BIRDO"),
    "TOP2_S1": ("top2", 1), "NO1_S2": ("s1", 2), "SCORE2_S1": ("s2", 1), "S1_1": ("s1", 1), "S1_2": ("s2", 1), "S1_TOP": ("s1", 1),
    "S1_RUNNERUP": ("s2", 1), "S1_TOTAL": ("top2", 1), "S1_T2": ("top2", 1), "S1_FIRST_PLACE_SCORE": ("s1", 1), "S1_P1": ("s1", 1), "S1_P2": ("s2", 1),
    "S1_LEADER_SCORE": ("s1", 1),
}
NAMES = [
    ({"symbol": "MK001", "name": "Race 1 Winner - Birdo", "market_name": "Mario Markets"}, ("race", 1, "BIRDO")),
    ({"symbol": "MK010", "name": "Series 1 Winner - Daisy"}, ("swin", 1, "DAISY")),
    ({"symbol": "MK020", "name": "Series 1 #1 Score"}, ("s1", 1)),
    ({"symbol": "MK021", "name": "Series 1 #2 Score"}, ("s2", 1)),
    ({"symbol": "MK022", "name": "Series 1 Top-2 Total"}, ("top2", 1)),
    ({"symbol": "MK030", "name": "Peach wins Race 6"}, ("race", 6, "PEACH")),
    ({"symbol": "MK031", "name": "Yoshi wins Series 2"}, ("swin", 2, "YOSHI")),
    ({"symbol": "MK032", "name": "Top Two Series Score (Series 2)"}, ("top2", 2)),
    ({"symbol": "MK033", "name": "Second-highest score, series 2"}, ("s2", 2)),
    # the mock's records: a terse code plus group and market fields that must not confuse the parse
    ({"symbol": "S1_NO1", "name": "S1 NO1", "group": "Series 1", "market_name": "Mario Markets"}, ("s1", 1)),
    ({"symbol": "R3_PEACH", "name": "R3 PEACH", "group": "Series 1", "market_name": "Mario Markets"}, ("race", 3, "PEACH")),
]


@pytest.mark.parametrize("symbol,role", sorted(CODES.items()))
def test_symbol_codes(symbol, role):
    assert guess_role({"symbol": symbol}) == role


@pytest.mark.parametrize("record,role", NAMES)
def test_descriptive_names(record, role):
    assert guess_role(record) == role


def test_unknown_is_unmapped():
    assert guess_role({"symbol": "OIL_0626_C100"}) is None
    assert guess_role({"symbol": "PORT", "name": "Cascadia Pacific Terminals"}) is None


@pytest.mark.parametrize("line,places", [
    ("1 2 5 9", [1, 2, 5, 9]),
    ("peach 5 birdo 1 yoshi 9 daisy 2", [1, 2, 5, 9]),
    ("5 peach 1 birdo 9 yoshi 2 daisy", [1, 2, 5, 9]),
    ("daisy=2 birdo=1 peach=5 yoshi=9", [1, 2, 5, 9]),
    ("Bir 3, Dai 1, Pea 7, Yos 2", [3, 1, 7, 2]),
])
def test_parse_race_accepts_positions_or_names_in_any_order(line, places):
    from mario.contracts import parse_race
    assert parse_race(line.split()) == places


@pytest.mark.parametrize("line", ["1 2 5", "1 1 5 9", "0 2 5 9", "peach 5 birdo 1 yoshi 9", "mario 1 daisy 2 peach 3 yoshi 4", "1 2 5 13"])
def test_parse_race_rejects_bad_input(line):
    from mario.contracts import parse_race
    with pytest.raises(ValueError):
        parse_race(line.split())


# ---- the live exchange (cornelltradingcompetition.org, read 2026-10-24): one series at a time, no series number in any symbol ----
LIVE = [
    ({"symbol": "TOP_PEA", "name": "Top Scorer: Peach", "group": "TOP"}, ("swin", 1, "PEACH")),
    ({"symbol": "TOP_BIR", "name": "Top Scorer: Birdo", "group": "TOP"}, ("swin", 1, "BIRDO")),
    ({"symbol": "RACE1_DAI", "name": "Race 1 Winner: Daisy", "group": "RACE1"}, ("race", 1, "DAISY")),
    ({"symbol": "RACE4_YOS", "name": "Race 4 Winner: Yoshi", "group": "RACE4"}, ("race", 4, "YOSHI")),
    ({"symbol": "SCORE_1ST", "name": "Top Scorer's Total Points", "group": "SCORE"}, ("s1", 1)),
    ({"symbol": "SCORE_2ND", "name": "Second Scorer's Total Points", "group": "SCORE"}, ("s2", 1)),
    ({"symbol": "SCORE_TOP2SUM", "name": "Sum of the Top Two Totals", "group": "SCORE"}, ("top2", 1)),
]


@pytest.mark.parametrize("record,role", LIVE)
def test_live_symbols_series_1(record, role):
    from mario.contracts import load_roles
    assert guess_role(record, series_hint=1) == role
    roles, unmapped = load_roles([record])           # no hint: series 1
    assert unmapped == [] and roles[record["symbol"]] == role


@pytest.mark.parametrize("record,role", LIVE)
def test_live_symbols_under_series_2(record, role):
    """Under "Mario Kart Series 2" the same names are series 2 contracts and RACE1 is race 5 of the tournament."""
    from mario.contracts import load_roles
    roles, unmapped = load_roles([record], series_hint=2)
    expect = ("race", role[1] + 4, role[2]) if role[0] == "race" else (role[0], 2) + role[2:]
    assert unmapped == [] and roles[record["symbol"]] == expect


def test_live_symbol_without_name_still_maps():
    assert guess_role({"symbol": "TOP_YOS"}, series_hint=1) == ("swin", 1, "YOSHI")
    assert guess_role({"symbol": "RACE3_PEA"}, series_hint=2) == ("race", 7, "PEACH")


def test_explicit_series_and_absolute_race_numbers_ignore_the_hint():
    assert guess_role({"symbol": "S1_WIN_PEACH"}, series_hint=2) == ("swin", 1, "PEACH")
    assert guess_role({"symbol": "R7_YOSHI"}, series_hint=2) == ("race", 7, "YOSHI")
    assert guess_role({"symbol": "SERIES1_SCORE1"}, series_hint=2) == ("s1", 1)


@pytest.mark.parametrize("name,series", [("Mario Kart Series 1", 1), ("Mario Kart Series 2", 2), ("mario kart series-2", 2), ("Mario Markets", None), (None, None)])
def test_series_from_competition(name, series):
    from mario.contracts import series_from_competition
    assert series_from_competition(name) == series


def test_hint_does_not_invent_roles_for_foreign_symbols():
    assert guess_role({"symbol": "OIL_0626_C100"}, series_hint=1) is None
    assert guess_role({"symbol": "PORT", "name": "Cascadia Pacific Terminals"}, series_hint=1) is None


@pytest.mark.parametrize("price,tick,text", [(36.0, 1.0, "36"), (36.4, 1.0, "36"), (36.6, 1, "37"), (48.237, 0.01, "48.24"), (48.2, None, "48.20"), (37.04, 0.1, "37.00")])
def test_price_formatted_on_the_tick(price, tick, text):
    from mario.tap import fmt_price
    assert fmt_price(price, tick) == text
