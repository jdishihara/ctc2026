"""Build derivs/desk.xlsx: a live-formula Black-Scholes desk sheet for the Derivatives case (no bots allowed, so
the humans trade from this). Sheets: Inputs, Contracts (12 contracts with fair, greeks, edge, market IV by Newton
steps), Analysts (scorecard and inverse-error weights), Timeline (10 events), Round3 (IV-linked quantity -> IV), Notes.

    python3 derivs/build_sheet.py            # writes derivs/desk.xlsx
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from pathlib import Path

BOLD = Font(bold=True); INPUT = PatternFill("solid", fgColor="FFF2CC"); HEAD = PatternFill("solid", fgColor="D9E1F2")
wb = Workbook()

# ---------------- Inputs ----------------
ws = wb.active; ws.title = "Inputs"
rows = [("Parameter", "Value", "Note"),
        ("OIL spot", 80.0, "underlying price shown on the exchange (cannot be traded)"),
        ("OIL IV", 0.40, "round 1: announced; round 2: your blend of the analysts (Analysts sheet); round 3: your estimate"),
        ("PLANE spot", 100.0, ""),
        ("PLANE IV", 0.50, ""),
        ("Rate r", 0.0, "fixed by the exchange calculator; set to match it"),
        ("Days to expiry", 20, "20 trading days at the case start; 19 in round 2, 18 in round 3 (one round = one day)"),
        ("Days per year", 252, ""),
        ("T (years)", "=B7/B8", "")]
for r in rows: ws.append(r)
for c in ("B2", "B3", "B4", "B5", "B6", "B7"): ws[c].fill = INPUT
for c in ws[1]: c.font = BOLD; c.fill = HEAD
ws.column_dimensions["A"].width = 16; ws.column_dimensions["C"].width = 90
names = {"S_OIL": "Inputs!$B$2", "IV_OIL": "Inputs!$B$3", "S_PLANE": "Inputs!$B$4", "IV_PLANE": "Inputs!$B$5", "R": "Inputs!$B$6", "T": "Inputs!$B$9"}

# ---------------- Contracts ----------------
cs = wb.create_sheet("Contracts")
hdr = ["Underlying", "Type", "Strike", "Bid", "Ask", "Mid", "S", "IV used", "d1", "d2", "Fair", "Delta", "Vega (per vol pt)", "Gamma",
       "Side", "Edge $", "Edge (vol pts)", "Market IV (mid)", "IV err", "Score"]
cs.append(hdr)
for c in cs[1]: c.font = BOLD; c.fill = HEAD; c.alignment = Alignment(wrap_text=True)
contracts = [("OIL", "call", 75), ("OIL", "call", 80), ("OIL", "call", 85), ("OIL", "put", 75), ("OIL", "put", 80), ("OIL", "put", 85),
             ("PLANE", "call", 90), ("PLANE", "call", 100), ("PLANE", "call", 110), ("PLANE", "put", 90), ("PLANE", "put", 100), ("PLANE", "put", 110)]
for i, (u, k, K) in enumerate(contracts, start=2):
    S = names["S_OIL"] if u == "OIL" else names["S_PLANE"]; IV = names["IV_OIL"] if u == "OIL" else names["IV_PLANE"]
    cs.append([u, k, K, None, None])
    cs[f"C{i}"].fill = INPUT; cs[f"D{i}"].fill = INPUT; cs[f"E{i}"].fill = INPUT
    cs[f"F{i}"] = f'=IF(AND(ISNUMBER(D{i}),ISNUMBER(E{i})),(D{i}+E{i})/2,"")'
    cs[f"G{i}"] = f"={S}"; cs[f"H{i}"] = f"={IV}"
    cs[f"I{i}"] = f"=(LN(G{i}/C{i})+({names['R']}+H{i}^2/2)*{names['T']})/(H{i}*SQRT({names['T']}))"
    cs[f"J{i}"] = f"=I{i}-H{i}*SQRT({names['T']})"
    if k == "call":
        cs[f"K{i}"] = f"=G{i}*NORM.S.DIST(I{i},TRUE)-C{i}*EXP(-{names['R']}*{names['T']})*NORM.S.DIST(J{i},TRUE)"
        cs[f"L{i}"] = f"=NORM.S.DIST(I{i},TRUE)"
    else:
        cs[f"K{i}"] = f"=C{i}*EXP(-{names['R']}*{names['T']})*NORM.S.DIST(-J{i},TRUE)-G{i}*NORM.S.DIST(-I{i},TRUE)"
        cs[f"L{i}"] = f"=NORM.S.DIST(I{i},TRUE)-1"
    cs[f"M{i}"] = f"=G{i}*NORM.S.DIST(I{i},FALSE)*SQRT({names['T']})/100"
    cs[f"N{i}"] = f"=NORM.S.DIST(I{i},FALSE)/(G{i}*H{i}*SQRT({names['T']}))"
    cs[f"O{i}"] = f'=IF(F{i}="","",IF(K{i}>E{i},"BUY",IF(K{i}<D{i},"SELL","-")))'
    cs[f"P{i}"] = f'=IF(F{i}="","",IF(K{i}>E{i},K{i}-E{i},IF(K{i}<D{i},D{i}-K{i},0)))'
    cs[f"Q{i}"] = f'=IF(OR(P{i}="",M{i}<0.000001),"",P{i}/M{i})'
    cs[f"R{i}"] = f'=IF(F{i}="","",IVcalc!R{i})'
    cs[f"S{i}"] = f'=IF(R{i}="","",(R{i}-H{i})*100)'
    cs[f"T{i}"] = f'=IF(P{i}="","",P{i}*ABS(L{i})^0)'          # placeholder: edge in dollars; sort by this
cs["A15"] = "Fill Strike/Bid/Ask (yellow) from the screen. Options trade at the MIDPOINT on this exchange, so Edge $ vs bid/ask is conservative: the real edge is Fair - Mid."
cs["A16"] = "Edge (vol pts) = Edge $ / Vega: compares contracts on one scale; the largest vega (at-the-money) contracts carry the most value per vol point of mispricing."
cs["A17"] = "After the makers snap (2 min after the news), Market IV should equal the true IV: that is the 'truth' column on the Analysts sheet."
for col, w in zip("ABCDEFGHIJKLMNOPQRST", [10, 6, 7, 7, 7, 7, 7, 8, 7, 7, 8, 7, 9, 8, 6, 8, 9, 10, 8, 8]): cs.column_dimensions[col].width = w

# ---------------- IVcalc: Newton iterations for market IV from the mid ----------------
iv = wb.create_sheet("IVcalc")
iv.append(["Row", "Mid", "S", "K", "call?", "iv0", "p0", "v0", "iv1", "p1", "v1", "iv2", "p2", "v2", "iv3", "p3", "v3", "iv"])
for c in iv[1]: c.font = BOLD; c.fill = HEAD
def bsp(S, K, ivc, call):   # price formula in Excel given cells
    d1 = f"((LN({S}/{K})+({names['R']}+{ivc}^2/2)*{names['T']})/({ivc}*SQRT({names['T']})))"
    d2 = f"({d1}-{ivc}*SQRT({names['T']}))"
    c = f"({S}*NORM.S.DIST({d1},TRUE)-{K}*EXP(-{names['R']}*{names['T']})*NORM.S.DIST({d2},TRUE))"
    p = f"({K}*EXP(-{names['R']}*{names['T']})*NORM.S.DIST(-{d2},TRUE)-{S}*NORM.S.DIST(-{d1},TRUE))"
    return f"IF({call},{c},{p})"
def vega(S, K, ivc):
    d1 = f"((LN({S}/{K})+({names['R']}+{ivc}^2/2)*{names['T']})/({ivc}*SQRT({names['T']})))"
    return f"({S}*NORM.S.DIST({d1},FALSE)*SQRT({names['T']}))"
for i in range(2, 14):
    iv[f"A{i}"] = i; iv[f"B{i}"] = f'=IF(Contracts!F{i}="",0,Contracts!F{i})'; iv[f"C{i}"] = f"=Contracts!G{i}"; iv[f"D{i}"] = f"=Contracts!C{i}"
    iv[f"E{i}"] = f'=Contracts!B{i}="call"'; iv[f"F{i}"] = f"=Contracts!H{i}"
    cols = ["F", "I", "L", "O"]
    for j, col in enumerate(cols):
        pc, vc = get_column_letter(iv[f"{col}1"].column + 1), get_column_letter(iv[f"{col}1"].column + 2)
        iv[f"{pc}{i}"] = f"={bsp(f'C{i}', f'D{i}', f'{col}{i}', f'E{i}')}"
        iv[f"{vc}{i}"] = f"={vega(f'C{i}', f'D{i}', f'{col}{i}')}"
        if j < 3:
            nxt = cols[j + 1]
            iv[f"{nxt}{i}"] = f"=MAX(0.01,MIN(3,{col}{i}-({pc}{i}-B{i})/MAX({vc}{i},0.0001)))"
    iv[f"R{i}"] = f'=IF(B{i}=0,"",MAX(0.01,MIN(3,O{i}-(P{i}-B{i})/MAX(Q{i},0.0001))))'
iv["A16"] = "Four Newton steps from the IV in use; accurate to <0.1 vol point for liquid strikes. Blank if no bid/ask."

# ---------------- Analysts ----------------
an = wb.create_sheet("Analysts")
an.append(["Event", "Underlying", "Analyst 1", "Analyst 2", "Analyst 3", "Truth (market IV after snap)", "Err 1 (vol pts)", "Err 2", "Err 3", "Note", "|Err 1|", "|Err 2|", "|Err 3|", "recent?"])
for c in an[1]: c.font = BOLD; c.fill = HEAD; c.alignment = Alignment(wrap_text=True)
r = 2
for ev in range(1, 11):
    for u in ("OIL", "PLANE"):
        an.append([ev, u, None, None, None, None])
        for col in "CDEF": an[f"{col}{r}"].fill = INPUT
        for k, col in enumerate("GHI"):
            src = "CDE"[k]; ab = "KLM"[k]
            an[f"{col}{r}"] = f'=IF(AND(ISNUMBER({src}{r}),ISNUMBER(F{r})),({src}{r}-F{r})*100,"")'
            an[f"{ab}{r}"] = f'=IF(ISNUMBER({col}{r}),ABS({col}{r}),"")'
        r += 1
R0, R1 = 2, r - 1
# recent? = 1 for the rows of the last 3 scored events (6 rows with a Truth), else 0
for i in range(R0, R1 + 1):
    an[f"N{i}"] = f'=IF(ISNUMBER(F{i}),IF(COUNT(F{i}:F${R1})<=6,1,0),0)'
base = r + 2
an[f"A{r+1}"] = "Scorecard (vol points)"; an[f"A{r+1}"].font = BOLD
labels = ["Mean abs error", "Bias", "n scored", "Inverse-error weight (all events)", "Mean abs error, last 3 events", "Inverse-error weight (last 3 events)"]
for j, lab in enumerate(labels): an[f"A{base+j}"] = lab
for k, col in enumerate("GHI"):
    out = "CDE"[k]; ab = "KLM"[k]
    an[f"{out}{base}"] = f'=IFERROR(AVERAGE({ab}{R0}:{ab}{R1}),"")'
    an[f"{out}{base+1}"] = f'=IFERROR(AVERAGE({col}{R0}:{col}{R1}),"")'
    an[f"{out}{base+2}"] = f"=COUNT({col}{R0}:{col}{R1})"
    an[f"{out}{base+3}"] = f'=IFERROR((1/MAX({out}{base},0.05))/((1/MAX($C${base},0.05))+(1/MAX($D${base},0.05))+(1/MAX($E${base},0.05))),"")'
    an[f"{out}{base+4}"] = f'=IFERROR(AVERAGEIFS({ab}{R0}:{ab}{R1},$N${R0}:$N${R1},1),"")'
    an[f"{out}{base+5}"] = f'=IFERROR((1/MAX({out}{base+4},0.05))/((1/MAX($C${base+4},0.05))+(1/MAX($D${base+4},0.05))+(1/MAX($E${base+4},0.05))),"")'
blend = base + 7
an[f"A{blend}"] = "Blend for the next event"; an[f"A{blend}"].font = BOLD
an[f"A{blend+1}"] = "Analyst estimates (next event)"
for col in "CDE": an[f"{col}{blend+1}"].fill = INPUT
an[f"A{blend+2}"] = "Weighted IV (all-event weights)"; an[f"B{blend+2}"] = f'=IFERROR(SUMPRODUCT(C{blend+1}:E{blend+1},C{base+3}:E{base+3}),AVERAGE(C{blend+1}:E{blend+1}))'
an[f"A{blend+3}"] = "Weighted IV (last-3-event weights)"; an[f"B{blend+3}"] = f'=IFERROR(SUMPRODUCT(C{blend+1}:E{blend+1},C{base+5}:E{base+5}),AVERAGE(C{blend+1}:E{blend+1}))'
an[f"A{blend+4}"] = "Median of the three"; an[f"B{blend+4}"] = f"=MEDIAN(C{blend+1}:E{blend+1})"
an[f"A{blend+6}"] = ("Round 1: IV is announced, so fill Truth directly and leave the analysts empty. Round 2: fill the three estimates when published, "
                     "then fill Truth from Contracts!R (market IV at the mid) two minutes after the news. Round 3: analysts give an IV-linked quantity; "
                     "record it in the estimate columns anyway and regress it on Truth once two events are in. Weights use 1/max(MAE, 0.05) so no analyst gets more than ~90%.")
an.column_dimensions["A"].width = 34; an.column_dimensions["F"].width = 16; an.column_dimensions["J"].width = 24
for col in "BCDEGHIKLM": an.column_dimensions[col].width = 11

# ---------------- Timeline ----------------
tl = wb.create_sheet("Timeline")
tl.append(["Event", "Round", "News (exchange time)", "Underlying moves", "Makers snap to fair", "Real-time offsets", "What to do"])
for c in tl[1]: c.font = BOLD; c.fill = HEAD; c.alignment = Alignment(wrap_text=True)
sched = [(1, 1, "06-01 09:30:00", "06-01 10:22:00", "06-01 11:14:00"), (2, 1, "06-01 11:40:00", "06-01 12:32:00", "06-01 13:24:00"), (3, 1, "06-01 13:50:00", "06-01 14:42:00", "06-01 15:34:00"),
         (4, 2, "06-02 09:30:00", "06-02 10:22:00", "06-02 11:14:00"), (5, 2, "06-02 11:40:00", "06-02 12:32:00", "06-02 13:24:00"), (6, 2, "06-02 13:50:00", "06-02 14:42:00", "06-02 15:34:00"),
         (7, 3, "06-03 09:30:00", "06-03 10:09:00", "06-03 10:48:00"), (8, 3, "06-03 11:07:30", "06-03 11:46:30", "06-03 12:25:30"), (9, 3, "06-03 12:45:00", "06-03 13:24:00", "06-03 14:03:00"), (10, 3, "06-03 14:22:30", "06-03 15:01:30", "06-03 15:40:30")]
todo = ("t+0: read the news, decide direction and IV change for OIL and PLANE; price all 12 at the NEW S and IV (Inputs); trade the biggest Edge(vol pts) before anyone moves. "
        "t+1 min: underlying moves to the new S (makers reprice delta, not vol): re-check edges at the new S. "
        "t+2 min: makers snap to the true IV: close or hold; record the market IV as Truth on the Analysts sheet. t+2.5 min: event over.")
for ev, rd, n, u, s in sched:
    tl.append([ev, rd, n, u, s, "news t, underlying t+1:00, snap t+2:00, event ends t+2:30 (real time)", todo if ev in (1, 4, 7) else ""])
tl.column_dimensions["C"].width = 18; tl.column_dimensions["D"].width = 18; tl.column_dimensions["E"].width = 18; tl.column_dimensions["F"].width = 40; tl.column_dimensions["G"].width = 100
for row in tl.iter_rows(min_row=2): 
    for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")

# ---------------- Round3: IV-linked quantity -> IV ----------------
r3 = wb.create_sheet("Round3")
r3.append(["Quantity the analysts publish", "Value (type here)", "Implied IV (annual)", "Daily vol", "1-day 1-sd move $ (S from Inputs)", "How it converts"])
for c in r3[1]: c.font = BOLD; c.fill = HEAD; c.alignment = Alignment(wrap_text=True)
r3["G1"] = "S used here (OIL by default; =Inputs!$B$4 for PLANE)"; r3["G2"] = f"={names['S_OIL']}"; r3["G2"].fill = INPUT
S_, T_ = "$G$2", names["T"]
rows3 = [
    ("Annual variance (sigma^2)", 0.16, "=SQRT(B{r})", "IV = sqrt(variance)"),
    ("Daily variance", 0.000635, "=SQRT(B{r}*252)", "IV = sqrt(252 x daily variance)"),
    ("Daily vol, fraction (sd of the 1-day return)", 0.0252, "=B{r}*SQRT(252)", "IV = daily vol x sqrt(252)"),
    ("Daily vol, percent", 2.52, "=B{r}/100*SQRT(252)", "IV = daily vol% / 100 x sqrt(252)"),
    ("Expected 1-day move, percent of spot (1 sd)", 2.52, "=B{r}/100*SQRT(252)", "IV = move% / 100 / sqrt(1/252)"),
    ("Expected 1-day move, dollars (1 sd)", 2.02, f"=B{{r}}/{S_}*SQRT(252)", "IV = move / S / sqrt(1/252)"),
    ("Expected move to expiry, percent of spot (1 sd)", 11.3, f"=B{{r}}/100/SQRT({T_})", "IV = move% / 100 / sqrt(T)"),
    ("ATM straddle price, dollars (contract expiry)", 6.82, None, "IV from 4 Newton steps on the straddle (2 x vega per step), start 0.4"),
    ("Weekly vol, percent (5-day sd)", 5.6, "=B{r}/100*SQRT(252/5)", "IV = weekly% / 100 x sqrt(252/5)"),
]
def straddle_formula(ivc):
    d1 = f"((LN(1)+({names['R']}+{ivc}^2/2)*{T_})/({ivc}*SQRT({T_})))"
    d2 = f"({d1}-{ivc}*SQRT({T_}))"
    call = f"({S_}*NORM.S.DIST({d1},TRUE)-{S_}*EXP(-{names['R']}*{T_})*NORM.S.DIST({d2},TRUE))"
    put = f"({S_}*EXP(-{names['R']}*{T_})*NORM.S.DIST(-{d2},TRUE)-{S_}*NORM.S.DIST(-{d1},TRUE))"
    veg = f"(2*{S_}*NORM.S.DIST({d1},FALSE)*SQRT({T_}))"
    return f"({call}+{put})", veg
for i, (label, example, f, how) in enumerate(rows3, start=2):
    r3[f"A{i}"] = label; r3[f"B{i}"] = example; r3[f"B{i}"].fill = INPUT
    if f is None:   # Newton steps in helper columns H..K
        prev = "0.4"
        for j, col in enumerate("HIJK"):
            st, vg = straddle_formula(prev)
            r3[f"{col}{i}"] = f"=MAX(0.01,MIN(3,{prev}-({st}-B{i})/MAX({vg},0.0001)))"
            prev = f"{col}{i}"
        r3[f"C{i}"] = f"=K{i}"
        r3["H1"] = "Newton 1"; r3["I1"] = "Newton 2"; r3["J1"] = "Newton 3"; r3["K1"] = "Newton 4"
    else:
        r3[f"C{i}"] = f.format(r=i)
    r3[f"D{i}"] = f"=C{i}/SQRT(252)"; r3[f"E{i}"] = f"={S_}*C{i}/SQRT(252)"; r3[f"F{i}"] = how
n3 = len(rows3) + 3
r3[f"A{n3}"] = "Round 3: the analysts stop publishing IV and publish 'a quantity linked to IV'. Type each analyst's number in the matching yellow cell: column C is the IV to put in Inputs (then weight analysts as in round 2)."
r3[f"A{n3+1}"] = "Check the first event against the makers' snap (market IV on the Contracts sheet 2 minutes after the news) to confirm which conversion the quantity follows; keep the row that matches. T and S come from Inputs."
r3[f"A{n3+2}"] = "python3 derivs/bs.py convert move_pct 2.52 --S 80 --T 18 does the same from the terminal (kinds: variance var_daily daily_vol daily_vol_pct move move_pct straddle straddle_pct vega_price)."
for col, w in zip("ABCDEFG", [46, 14, 16, 10, 22, 60, 16]): r3.column_dimensions[col].width = w
for row in r3.iter_rows(min_row=2):
    for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")

# ---------------- Notes ----------------
no = wb.create_sheet("Notes")
for line in ["Derivatives case (35% of the overall score): European options on OIL and PLANE, 3 calls + 3 puts each, one expiry 20 trading days after the start.",
             "No bots. Options trade at the MIDPOINT of the quoted market. PnL is computed at the end of each round once the underlying is revealed.",
             "Score = sum over rounds of (round rank)^1.5, lower is better: a terrible round costs more than a great round earns. Protect against the tail: size by vega, keep net vega near zero when you have no view on IV.",
             "Round 1: IV announced with each event. Round 2: three analysts publish IV estimates (score them here; weights update after every event). Round 3: analysts publish an IV-linked quantity; regress it on realised IV from rounds 1-2 if it looks like a variance, a range or a vol-of-vol.",
             "Bots: 1 minute after the news the underlying moves; 2 minutes after the news the option makers snap to the correct IV. So the window to sell mispriced options is the 2 minutes after the news, and the window to collect is the snap.",
             "Checklist per event: (1) write the headline and your S, IV guesses; (2) Inputs -> new S and IV; (3) sort Contracts by Edge (vol pts); (4) trade at most 2-3 contracts, largest vega first; (5) at the snap record Truth on Analysts; (6) flatten or hold with a reason.",
             "Sanity: at-the-money vega ~ S*0.4*sqrt(T)/100 per vol point; with S=80, T=20 days (0.079 y): about 0.09 per vol point per contract. A 5-vol-point mispricing is about 0.45 per contract.",
             "Formulas use NORM.S.DIST (Excel 2010+ / Google Sheets / LibreOffice). Market IV uses four Newton steps from the IV in Inputs."]:
    no.append([line])
no.column_dimensions["A"].width = 160
for row in no.iter_rows():
    for c in row: c.alignment = Alignment(wrap_text=True, vertical="top")

out = Path(__file__).resolve().parent / "desk.xlsx"; wb.save(out); print("wrote", out)
