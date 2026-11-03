"""Tipo comum usado pelas verificações de saúde (banco, broker)."""
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CheckResult:
    ok: bool
    latency_ms: float | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
