from __future__ import annotations

import pytest

from fastapi_limitex.errors import ConfigurationError
from fastapi_limitex.rate import RateLimitItem, parse, parse_many


@pytest.mark.parametrize(
    ("expression", "amount", "multiples", "granularity"),
    [
        ("5/minute", 5, 1, 60),
        ("5 / minute", 5, 1, 60),
        ("100 per hour", 100, 1, 3600),
        ("10/5 minutes", 10, 5, 60),
        ("10/5minutes", 10, 5, 60),
        ("1/second", 1, 1, 1),
        ("2/day", 2, 1, 86_400),
        ("3/week", 3, 1, 604_800),
        ("7/2h", 7, 2, 3600),
    ],
)
def test_parse_valid(expression: str, amount: int, multiples: int, granularity: int) -> None:
    item = parse(expression)
    assert item.amount == amount
    assert item.multiples == multiples
    assert item.granularity_seconds == granularity
    assert item.expiry == multiples * granularity


def test_parse_item_passthrough() -> None:
    item = RateLimitItem(5, 1, 60)
    assert parse(item) is item


@pytest.mark.parametrize("expression", ["", "abc", "5/parsec", "0/minute", "5/0minute", "/minute"])
def test_parse_invalid(expression: str) -> None:
    with pytest.raises(ConfigurationError):
        parse(expression)


def test_parse_many_from_string_list() -> None:
    items = parse_many("5/second; 100/hour")
    assert [i.amount for i in items] == [5, 100]


def test_parse_many_from_list() -> None:
    items = parse_many(["5/second", RateLimitItem(100, 1, 3600)])
    assert len(items) == 2
    assert items[1].amount == 100


def test_parse_many_empty_raises() -> None:
    with pytest.raises(ConfigurationError):
        parse_many([])


def test_scope_is_stable() -> None:
    assert parse("5/minute").scope() == parse("5/minute").scope()
    assert parse("5/minute").scope() != parse("6/minute").scope()
