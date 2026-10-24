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
