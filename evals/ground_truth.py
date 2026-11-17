"""Ground truth answers used to score agent responses in evals."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Case:
    """A single eval case: a query and the answer we expect."""

    query: str
    expected: object
    tags: tuple[str, ...] = field(default_factory=tuple)


CASES: tuple[Case, ...] = (
    Case(
        query="list available symbols",
        expected="symbol list matches data directory",
        tags=("smoke",),
    ),
)


def cases(tag: str | None = None) -> list[Case]:
    """Return eval cases, optionally filtered by tag."""
    if tag is None:
        return list(CASES)
    return [case for case in CASES if tag in case.tags]