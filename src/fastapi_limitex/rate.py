from __future__ import annotations

import re
from dataclasses import dataclass

from fastapi_limitex.errors import ConfigurationError

_GRANULARITIES: dict[str, int] = {
    "second": 1,
    "seconds": 1,
    "sec": 1,
    "s": 1,
    "minute": 60,
    "minutes": 60,
    "min": 60,
    "m": 60,
    "hour": 3600,
    "hours": 3600,
    "hr": 3600,
    "h": 3600,
    "day": 86_400,
    "days": 86_400,
    "d": 86_400,
    "week": 604_800,
    "weeks": 604_800,
    "w": 604_800,
    "month": 2_592_000,
    "months": 2_592_000,
    "mo": 2_592_000,
    "year": 31_536_000,
    "years": 31_536_000,
    "y": 31_536_000,
}

_EXPRESSION = re.compile(
    r"^\s*(?P<amount>\d+)\s*(?:/|\s+per\s+)\s*(?P<multiples>\d+)?\s*(?P<unit>[a-zA-Z]+)\s*$"
)


@dataclass(frozen=True)
class RateLimitItem:
    """An immutable, parsed rate limit.

    Attributes:
        amount: The number of requests permitted within the window.
        multiples: The number of granularity units that form the window.
        granularity_seconds: The number of seconds in a single granularity unit.
    """

    amount: int
    multiples: int
    granularity_seconds: int

    @property
    def expiry(self) -> int:
        """Return the length of the window in seconds."""
        return self.granularity_seconds * self.multiples

    def scope(self) -> str:
        """Return a stable string identifying this limit's window shape."""
        return f"{self.amount}/{self.multiples}/{self.granularity_seconds}"

    def __str__(self) -> str:
        return f"{self.amount} per {self.multiples} x {self.granularity_seconds}s"


StaticLimit = str | RateLimitItem | list[str | RateLimitItem]
"""A rate limit that does not depend on the incoming request."""


def parse(expression: str | RateLimitItem) -> RateLimitItem:
    """Parse a single rate limit expression into a :class:`RateLimitItem`.

    Accepts forms such as ``"5/minute"``, ``"10/5 minutes"``, ``"100 per hour"``
    and ``"1/second"``. Passing an existing :class:`RateLimitItem` returns it
    unchanged.

    Raises:
        ConfigurationError: If the expression cannot be parsed.
    """
    if isinstance(expression, RateLimitItem):
        return expression
    match = _EXPRESSION.match(expression)
    if match is None:
        raise ConfigurationError(f"Could not parse rate limit expression: {expression!r}")
    unit = match.group("unit").lower()
    if unit not in _GRANULARITIES:
        raise ConfigurationError(
            f"Unknown time unit {unit!r} in {expression!r}. "
            f"Supported units: second, minute, hour, day, week, month, year."
        )
    amount = int(match.group("amount"))
    multiples = int(match.group("multiples") or 1)
    if amount <= 0 or multiples <= 0:
        raise ConfigurationError(f"Rate limit values must be positive: {expression!r}")
    return RateLimitItem(
        amount=amount,
        multiples=multiples,
        granularity_seconds=_GRANULARITIES[unit],
    )


def parse_many(
    expressions: StaticLimit,
) -> list[RateLimitItem]:
    """Parse one or more rate limits into a list of :class:`RateLimitItem`.

    A single string may contain several limits separated by ``;`` or ``,``.
    """
    if isinstance(expressions, (str, RateLimitItem)):
        raw: list[str | RateLimitItem] = [expressions]
    else:
        raw = list(expressions)
    items: list[RateLimitItem] = []
    for entry in raw:
        if isinstance(entry, str):
            for part in re.split(r"[;,]", entry):
                if part.strip():
                    items.append(parse(part))
        else:
            items.append(parse(entry))
    if not items:
        raise ConfigurationError("At least one rate limit must be provided.")
    return items
