"""TDD tests for TenpoParser against real .eml fixtures."""

import os
from decimal import Decimal
from pathlib import Path

import pytest

from app.parsers.tenpo import TenpoParser
from tests.helpers import load_eml

FIXTURES = Path(__file__).parent / "fixtures" / "tenpo"


@pytest.fixture
def parser() -> TenpoParser:
    return TenpoParser()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _eml(name: str) -> dict:
    return load_eml(FIXTURES / name)


# ---------------------------------------------------------------------------
# can_parse
# ---------------------------------------------------------------------------


def test_can_parse_compra_normal(parser: TenpoParser):
    assert parser.can_parse(_eml("compra_normal.eml")) is True


def test_can_parse_comprobante_transferencia(parser: TenpoParser):
    assert parser.can_parse(_eml("comprobante_transferencia.eml")) is True


def test_can_parse_pago_tarjeta(parser: TenpoParser):
    assert parser.can_parse(_eml("pago_tarjeta.eml")) is True


# ---------------------------------------------------------------------------
# compra_normal — expense
# ---------------------------------------------------------------------------


def test_compra_normal_amount(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal.eml"))
    assert result is not None
    assert result.amount == Decimal("12000")


def test_compra_normal_merchant(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal.eml"))
    assert result is not None
    assert "MERCADOPAGO" in result.merchant or "KRISPYKR" in result.merchant


def test_compra_normal_transaction_type(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal.eml"))
    assert result is not None
    assert result.transaction_type == "expense"


def test_compra_normal_source(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal.eml"))
    assert result is not None
    assert result.source == "tenpo"


def test_compra_normal_date(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal.eml"))
    assert result is not None
    assert result.transaction_date.day == 10
    assert result.transaction_date.month == 4
    assert result.transaction_date.year == 2026


# ---------------------------------------------------------------------------
# compra_normal2 — expense (Uber Eats, larger amount)
# ---------------------------------------------------------------------------


def test_compra_normal2_amount(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal2.eml"))
    assert result is not None
    assert result.amount == Decimal("61255")


def test_compra_normal2_merchant(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal2.eml"))
    assert result is not None
    assert "UBER EATS" in result.merchant


def test_compra_normal2_transaction_type(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal2.eml"))
    assert result is not None
    assert result.transaction_type == "expense"


# ---------------------------------------------------------------------------
# compra_normal3 — expense (subscription, international)
# ---------------------------------------------------------------------------


def test_compra_normal3_amount(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal3.eml"))
    assert result is not None
    assert result.amount == Decimal("223366")


def test_compra_normal3_merchant(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal3.eml"))
    assert result is not None
    assert "CLAUDE" in result.merchant


def test_compra_normal3_transaction_type(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal3.eml"))
    assert result is not None
    assert result.transaction_type == "expense"


# ---------------------------------------------------------------------------
# compra_normal4 — expense (supermarket)
# ---------------------------------------------------------------------------


def test_compra_normal4_amount(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal4.eml"))
    assert result is not None
    assert result.amount == Decimal("131833")


def test_compra_normal4_merchant(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal4.eml"))
    assert result is not None
    assert "JUMBO" in result.merchant


def test_compra_normal4_transaction_type(parser: TenpoParser):
    result = parser.parse(_eml("compra_normal4.eml"))
    assert result is not None
    assert result.transaction_type == "expense"


# ---------------------------------------------------------------------------
# comprobante_transferencia — income (received transfer)
# ---------------------------------------------------------------------------


def test_comprobante_transferencia_amount(parser: TenpoParser):
    result = parser.parse(_eml("comprobante_transferencia.eml"))
    assert result is not None
    assert result.amount == Decimal("800000")


def test_comprobante_transferencia_transaction_type(parser: TenpoParser):
    result = parser.parse(_eml("comprobante_transferencia.eml"))
    assert result is not None
    assert result.transaction_type == "income"


def test_comprobante_transferencia_merchant(parser: TenpoParser):
    result = parser.parse(_eml("comprobante_transferencia.eml"))
    assert result is not None
    # Merchant is the transfer sender name
    assert result.merchant != ""


def test_comprobante_transferencia_date(parser: TenpoParser):
    result = parser.parse(_eml("comprobante_transferencia.eml"))
    assert result is not None
    assert result.transaction_date.day == 8
    assert result.transaction_date.month == 5
    assert result.transaction_date.year == 2026


# ---------------------------------------------------------------------------
# pago_tarjeta — credit card payment (expense in Phase 1)
# ---------------------------------------------------------------------------


def test_pago_tarjeta_amount(parser: TenpoParser):
    result = parser.parse(_eml("pago_tarjeta.eml"))
    assert result is not None
    assert result.amount == Decimal("1212170")


def test_pago_tarjeta_merchant(parser: TenpoParser):
    result = parser.parse(_eml("pago_tarjeta.eml"))
    assert result is not None
    assert result.merchant == "TENPO CREDITO"


def test_pago_tarjeta_transaction_type(parser: TenpoParser):
    result = parser.parse(_eml("pago_tarjeta.eml"))
    assert result is not None
    assert result.transaction_type == "expense"


# ---------------------------------------------------------------------------
# pago_tarjeta2 — same as pago_tarjeta (duplicate fixture)
# ---------------------------------------------------------------------------


def test_pago_tarjeta2_amount(parser: TenpoParser):
    result = parser.parse(_eml("pago_tarjeta2.eml"))
    assert result is not None
    assert result.amount == Decimal("1212170")


def test_pago_tarjeta2_transaction_type(parser: TenpoParser):
    result = parser.parse(_eml("pago_tarjeta2.eml"))
    assert result is not None
    assert result.transaction_type == "expense"


# ---------------------------------------------------------------------------
# Negative cases — publicidad and estado_cuenta should NOT yield transactions
# ---------------------------------------------------------------------------


def test_publicidad_returns_none(parser: TenpoParser):
    """Advertising emails should not produce ParsedTransaction."""
    email_data = _eml("publicidad.eml")
    # can_parse may be True (same domain), but parse must return None
    result = parser.parse(email_data)
    assert result is None


def test_publicidad2_returns_none(parser: TenpoParser):
    email_data = _eml("publicidad2.eml")
    result = parser.parse(email_data)
    assert result is None
