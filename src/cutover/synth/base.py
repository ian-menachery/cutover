"""The legacy export: a fictional insurer's policy-admin system, seeded.

Everything here is invented. Names are drawn from generic word lists; any
resemblance to a real person or business is coincidence. Values are written
the way old flat-file exports look: upper case, MM/DD/YYYY, coded picklists,
money as text with thousands separators.
"""

import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

FIRST = [
    "JAMES",
    "MARY",
    "ROBERT",
    "PATRICIA",
    "JOHN",
    "JENNIFER",
    "MICHAEL",
    "LINDA",
    "DAVID",
    "ELIZABETH",
    "WILLIAM",
    "SUSAN",
    "RICHARD",
    "JESSICA",
    "JOSEPH",
    "SARAH",
    "THOMAS",
    "KAREN",
    "CARLOS",
    "NANCY",
    "DANIEL",
    "LISA",
    "MATTHEW",
    "BETTY",
    "ANTHONY",
    "SANDRA",
    "MARK",
    "ASHLEY",
    "PRIYA",
    "KEVIN",
    "ANH",
    "EMILY",
    "RYAN",
    "DONNA",
    "WEI",
    "MICHELLE",
    "OMAR",
    "AMANDA",
]
LAST = [
    "SMITH",
    "JOHNSON",
    "WILLIAMS",
    "BROWN",
    "JONES",
    "GARCIA",
    "MILLER",
    "DAVIS",
    "RODRIGUEZ",
    "MARTINEZ",
    "HERNANDEZ",
    "LOPEZ",
    "GONZALEZ",
    "WILSON",
    "ANDERSON",
    "THOMAS",
    "TAYLOR",
    "MOORE",
    "JACKSON",
    "MARTIN",
    "LEE",
    "PEREZ",
    "THOMPSON",
    "WHITE",
    "HARRIS",
    "SANCHEZ",
    "CLARK",
    "RAMIREZ",
    "LEWIS",
    "ROBINSON",
    "WALKER",
    "YOUNG",
    "ALLEN",
    "KING",
    "WRIGHT",
    "SCOTT",
    "TORRES",
    "NGUYEN",
    "HILL",
    "FLORES",
    "GREEN",
    "ADAMS",
    "NELSON",
    "BAKER",
    "HALL",
    "RIVERA",
    "CAMPBELL",
    "MITCHELL",
    "CARTER",
    "ROBERTS",
    "PATEL",
    "OKAFOR",
    "KOWALSKI",
    "FITZGERALD",
    "MACDONALD",
    "CHRISTENSEN",
    "VANDERBERG",
    "OYELARAN",
]
PLACE = [
    "NORTHFIELD",
    "HARBOR",
    "SUMMIT",
    "PIONEER",
    "LAKESIDE",
    "GRANITE",
    "MERIDIAN",
    "BAYVIEW",
    "CEDAR",
    "RIVERBEND",
    "KESTREL",
    "IRONWOOD",
    "SILVERLAKE",
    "FOXHOLLOW",
    "BRIARWOOD",
    "ASHFORD",
    "COPPERLINE",
    "MAPLEGROVE",
]
TRADE = [
    "TOOL & DIE",
    "LOGISTICS",
    "DENTAL GROUP",
    "MANUFACTURING",
    "PROPERTY MANAGEMENT",
    "AUTO BODY",
    "LANDSCAPING",
    "ELECTRIC SUPPLY",
    "FAMILY PRACTICE",
    "BUILDERS",
    "PLUMBING & HEATING",
    "BAKERY",
]
SUFFIX = ("INC", "LLC", "CO", "CORP")
STATES = [
    "MA",
    "NY",
    "CT",
    "NJ",
    "PA",
    "OH",
    "IL",
    "TX",
    "FL",
    "GA",
    "NC",
    "VA",
    "MI",
    "WI",
    "MN",
    "CO",
    "AZ",
    "WA",
    "OR",
    "CA",
]

PLANS = (("TL10", 15), ("TL20", 25), ("TL30", 15), ("WL", 20), ("UL", 15), ("DI", 10))
MODES = (("A", 30), ("S", 12), ("Q", 18), ("M", 40))
RATES = {
    "TL10": (12, 25),
    "TL20": (18, 35),
    "TL30": (25, 50),
    "WL": (100, 220),
    "UL": (60, 140),
    "DI": (200, 450),
}  # premium per 10,000 of face (DI: of annual benefit)
FACES = (50_000, 100_000, 150_000, 250_000, 300_000, 500_000, 750_000, 1_000_000)
POLICIES_PER_ACCOUNT = ((1, 25), (2, 30), (3, 22), (4, 13), (5, 10))
LAST_DAY = date(2024, 6, 30)
PENDING = 4  # policies deferred to manual migration, ticket MIG-142


def _pick(rng: random.Random, weighted) -> str:
    values, weights = zip(*weighted, strict=True)
    return rng.choices(values, weights=weights)[0]


def _day(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def legacy_date(d: date) -> str:
    return d.strftime("%m/%d/%Y")


def legacy_money(x: Decimal) -> str:
    return f"{x:,.2f}"


def _name(rng: random.Random, kind: str) -> str:
    first, last = rng.choice(FIRST), rng.choice(LAST)
    if kind == "I":
        return f"{last}, {first} {rng.choice('ABCDEFGHJKLMNPRSTW')}"
    if kind == "G":
        return f"{rng.choice(PLACE)} {rng.choice(TRADE)} {rng.choice(SUFFIX)}"
    return rng.choice(
        (
            f"THE {last} FAMILY TRUST",
            f"{last} {first} REVOCABLE LIVING TRUST",
            f"THE {first} AND {rng.choice(FIRST)} {last} TRUST",
        )
    )


def make_legacy(seed: int, n_accounts: int) -> dict[str, list[dict[str, str]]]:
    rng = random.Random(seed)
    accounts, policies = [], []
    cust_no, pol_no = 10_000_000 + rng.randint(0, 9_999), 100_000_000 + rng.randint(0, 99_999)

    for _ in range(n_accounts):
        cust_no += rng.randint(1, 60)
        kind = _pick(rng, (("I", 80), ("G", 12), ("T", 8)))
        opened = _day(rng, date(1988, 1, 1), date(2022, 12, 31))
        accounts.append(
            {
                "CUST_NO": f"{cust_no:08d}",
                "CUST_NAME": _name(rng, kind),
                "CUST_TYPE": kind,
                "ST": rng.choice(STATES),
                "OPEN_DT": legacy_date(opened),
                "STATUS": "A" if rng.random() < 0.9 else "I",
            }
        )
        for _ in range(int(_pick(rng, POLICIES_PER_ACCOUNT))):
            pol_no += rng.randint(1, 400)
            plan = _pick(rng, PLANS)
            face = (
                rng.choice((12_000, 24_000, 36_000, 60_000, 96_000))
                if plan == "DI"
                else (rng.choice(FACES))
            )
            rate = Decimal(rng.randint(*RATES[plan])) / Decimal(10_000)
            premium = (Decimal(face) * rate * Decimal(rng.randint(90, 110)) / 100).quantize(
                Decimal("0.01"), ROUND_HALF_UP
            )
            issued = _day(rng, max(opened, date(1990, 1, 1)), LAST_DAY - timedelta(days=400))
            roll = rng.random()
            status, lapsed = "IF", ""
            if roll < 0.18:
                status = "LP"
                lapsed = legacy_date(_day(rng, issued + timedelta(days=365), LAST_DAY))
            elif roll < 0.24 and plan in ("WL", "UL"):
                status = "PU"
            policies.append(
                {
                    "POL_NO": f"P{pol_no:09d}",
                    "CUST_NO": f"{cust_no:08d}",
                    "PLAN_CD": plan,
                    "MODE": _pick(rng, MODES),
                    "ANN_PREM": legacy_money(premium),
                    "FACE_AMT": legacy_money(Decimal(face)),
                    "ISSUE_DT": legacy_date(issued),
                    "STATUS": status,
                    "LAPSE_DT": lapsed,
                }
            )

    in_force = [p for p in policies if p["STATUS"] == "IF"]
    for p in rng.sample(in_force, PENDING):
        p["STATUS"] = "PN"
    return {"accounts": accounts, "policies": policies}
