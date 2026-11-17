"""A four-policy migration small enough to reason about by hand.

P3 lapsed in 2020, so it is in scope; P4 lapsed in 2017, so the scope rule
excludes it and the correct ETL never loads it.
"""

import copy

import pytest

from cutover.migration import load_migration
from cutover.runner import run_checks
from cutover.spec import DEFAULT_SPEC, load_spec
from cutover.synth.etl import migrate
from cutover.synth.scenario import write_tables

SPEC = load_spec(DEFAULT_SPEC)

LEGACY = {
    "accounts": [
        {
            "CUST_NO": "00000001",
            "CUST_NAME": "SMITH, JOHN A",
            "CUST_TYPE": "I",
            "ST": "MA",
            "OPEN_DT": "01/15/2001",
            "STATUS": "A",
        },
        {
            "CUST_NO": "00000002",
            "CUST_NAME": "THE LEE FAMILY TRUST",
            "CUST_TYPE": "T",
            "ST": "NY",
            "OPEN_DT": "06/30/1999",
            "STATUS": "A",
        },
        {
            "CUST_NO": "00000003",
            "CUST_NAME": "HARBOR BAKERY LLC",
            "CUST_TYPE": "G",
            "ST": "CT",
            "OPEN_DT": "11/02/2010",
            "STATUS": "I",
        },
    ],
    "policies": [
        {
            "POL_NO": "P000000001",
            "CUST_NO": "00000001",
            "PLAN_CD": "TL20",
            "MODE": "M",
            "ANN_PREM": "1,234.56",
            "FACE_AMT": "500,000.00",
            "ISSUE_DT": "02/10/2005",
            "STATUS": "IF",
            "LAPSE_DT": "",
        },
        {
            "POL_NO": "P000000002",
            "CUST_NO": "00000001",
            "PLAN_CD": "WL",
            "MODE": "S",
            "ANN_PREM": "3,000.00",
            "FACE_AMT": "250,000.00",
            "ISSUE_DT": "07/04/2008",
            "STATUS": "PU",
            "LAPSE_DT": "",
        },
        {
            "POL_NO": "P000000003",
            "CUST_NO": "00000002",
            "PLAN_CD": "UL",
            "MODE": "A",
            "ANN_PREM": "2,100.00",
            "FACE_AMT": "300,000.00",
            "ISSUE_DT": "03/03/2012",
            "STATUS": "LP",
            "LAPSE_DT": "05/01/2020",
        },
        {
            "POL_NO": "P000000004",
            "CUST_NO": "00000003",
            "PLAN_CD": "DI",
            "MODE": "Q",
            "ANN_PREM": "900.00",
            "FACE_AMT": "36,000.00",
            "ISSUE_DT": "12/25/2015",
            "STATUS": "LP",
            "LAPSE_DT": "08/15/2017",
        },
    ],
}


def by(rows, col, value):
    return next(r for r in rows if r[col] == value)


@pytest.fixture
def mini(tmp_path):
    """Run the checks on the mini migration after ``mutate(legacy, target)``."""

    def run(mutate=None, register=()):
        legacy = copy.deepcopy(LEGACY)
        target = migrate(legacy, SPEC)
        if mutate:
            mutate(legacy, target)
        write_tables(tmp_path, SPEC, {"source": legacy, "target": target}, list(register))
        return run_checks(load_migration(tmp_path, SPEC))

    return run


def findings(report, check_id):
    return next(c for c in report.checks if c.id == check_id).findings
