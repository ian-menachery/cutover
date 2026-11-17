"""The mapping spec: the signed-off mapping workbook, as data.

Loaded from JSON into frozen dataclasses. No I/O beyond reading the one file,
no DuckDB. Every check reads the migration through this.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

TRANSFORMS = {"text", "date", "money", "map", "parent"}
CLASSES = {"key", "money", "date", "picklist", "text"}


@dataclass(frozen=True)
class FieldSpec:
    source: str
    target: str
    cls: str
    transform: str
    required: bool = False
    format: str | None = None
    value_map: dict[str, str] = field(default_factory=dict)
    parent: str | None = None


@dataclass(frozen=True)
class ScopeCondition:
    """One clause of a scope exclusion. A row is excluded when every clause holds."""

    field: str
    equals: str | None = None
    before: str | None = None
    format: str | None = None


@dataclass(frozen=True)
class EntitySpec:
    name: str
    source_file: str
    target_file: str
    source_key: str
    target_key: str
    target_id: str
    fields: tuple[FieldSpec, ...]
    exclude_when: tuple[ScopeCondition, ...] = ()
    group_by: tuple[str, ...] = ()
    sums: tuple[str, ...] = ()

    def field(self, target: str) -> FieldSpec:
        for f in self.fields:
            if f.target == target:
                return f
        raise KeyError(f"{self.name} has no mapped field {target!r}")


@dataclass(frozen=True)
class Spec:
    name: str
    target_date_format: str
    entities: tuple[EntitySpec, ...]

    def entity(self, name: str) -> EntitySpec:
        for e in self.entities:
            if e.name == name:
                return e
        raise KeyError(f"spec has no entity {name!r}")


def _field(raw: dict) -> FieldSpec:
    t = raw["transform"]
    if t["type"] not in TRANSFORMS:
        raise ValueError(f"unknown transform {t['type']!r} on {raw['target']}")
    if raw["class"] not in CLASSES:
        raise ValueError(f"unknown class {raw['class']!r} on {raw['target']}")
    return FieldSpec(
        source=raw["source"],
        target=raw["target"],
        cls=raw["class"],
        transform=t["type"],
        required=bool(raw.get("required", False)),
        format=t.get("format"),
        value_map=dict(t.get("map", {})),
        parent=t.get("entity"),
    )


def _entity(raw: dict) -> EntitySpec:
    totals = raw.get("control_totals", {})
    return EntitySpec(
        name=raw["name"],
        source_file=raw["source_file"],
        target_file=raw["target_file"],
        source_key=raw["source_key"],
        target_key=raw["target_key"],
        target_id=raw["target_id"],
        fields=tuple(_field(f) for f in raw["fields"]),
        exclude_when=tuple(ScopeCondition(**c) for c in raw.get("exclude_when", [])),
        group_by=tuple(totals.get("group_by", [])),
        sums=tuple(totals.get("sum", [])),
    )


def parse_spec(raw: dict) -> Spec:
    spec = Spec(
        name=raw["name"],
        target_date_format=raw.get("target_date_format", "%Y-%m-%d"),
        entities=tuple(_entity(e) for e in raw["entities"]),
    )
    names = {e.name for e in spec.entities}
    for e in spec.entities:
        for f in e.fields:
            if f.transform == "parent" and f.parent not in names:
                raise ValueError(f"{e.name}.{f.target} points at unknown entity {f.parent!r}")
    return spec


def load_spec(path: str | Path) -> Spec:
    return parse_spec(json.loads(Path(path).read_text(encoding="utf-8")))


DEFAULT_SPEC = Path(__file__).resolve().parents[2] / "spec" / "mapping.json"
