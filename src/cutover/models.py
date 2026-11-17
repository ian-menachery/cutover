"""Result models. Plain dataclasses; `to_dict` gives the JSON the site port matches.

Row numbers are CSV line numbers: the header is row 1, the first record row 2,
so a ref matches the row a reviewer sees when opening the file in a spreadsheet.
"""

from dataclasses import asdict, dataclass, field

PASS, FAIL, SKIP = "pass", "fail", "skip"
BLOCKER, WARNING = "blocker", "warning"


@dataclass
class Finding:
    check: str
    severity: str
    entity: str
    kind: str
    message: str
    key: str | None = None
    source_row: int | None = None
    target_row: int | None = None
    field: str | None = None
    group: dict[str, str | None] | None = None
    source_value: str | None = None
    expected: str | None = None
    found: str | None = None
    waived: bool = False
    ticket: str | None = None


@dataclass
class CheckResult:
    id: str
    name: str
    status: str
    message: str
    findings: list[Finding] = field(default_factory=list)


@dataclass(frozen=True)
class RegisterEntry:
    """One accepted difference from the exception register."""

    check: str
    entity: str
    key: str
    reason: str
    ticket: str


@dataclass
class Report:
    spec: str
    checks: list[CheckResult]
    readiness: dict

    def to_dict(self) -> dict:
        return asdict(self)
