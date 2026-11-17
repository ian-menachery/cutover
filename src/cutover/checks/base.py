"""What every check shares: the Check record and the table requirements."""

from collections.abc import Callable
from dataclasses import dataclass

from cutover.migration import Migration
from cutover.models import Finding
from cutover.spec import Spec


@dataclass(frozen=True)
class Check:
    id: str
    name: str
    run: Callable[[Migration], list[Finding]]
    requires: Callable[[Spec], list[str]]


def both_sides(spec: Spec) -> list[str]:
    return [f"{side}_{e.name}" for e in spec.entities for side in ("src", "tgt")]


def target_side(spec: Spec) -> list[str]:
    return [f"tgt_{e.name}" for e in spec.entities]


def show(value) -> str | None:
    return None if value is None else str(value)


def blank(value) -> str:
    return "blank" if value is None else str(value)
