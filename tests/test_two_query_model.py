import pytest

from quant_stickynote.query_engine import QueryDefinition


def test_query_definition_requires_symbol_and_price_queries():
    definition = {
        "id": "momentum_example",
        "name": "Momentum Example",
        "enabled": True,
        "external_database": {"url": "sqlite:///:memory:"},
        "symbol_query": "SELECT 'AAPL' AS symbol UNION ALL SELECT 'MSFT' AS symbol",
        "price_query": "SELECT symbol, price FROM prices WHERE symbol = :symbol",
        "signal_extraction": {
            "symbol_column": "symbol",
            "buy_price_column": "price",
            "trigger_reason_template": "Momentum signal",
        },
    }

    query = QueryDefinition(definition)

    assert query.symbol_query == definition["symbol_query"]
    assert query.price_query == definition["price_query"]


def test_query_definition_rejects_missing_symbol_or_price_query():
    with pytest.raises(ValueError):
        QueryDefinition({
            "id": "bad_query",
            "name": "Bad query",
            "enabled": True,
            "external_database": {"url": "sqlite:///:memory:"},
            "symbol_query": "SELECT 'AAPL' AS symbol",
            "signal_extraction": {
                "symbol_column": "symbol",
                "buy_price_column": "price",
            },
        })
