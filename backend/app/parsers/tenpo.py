import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.parsers.base import BaseParser, ParsedTransaction

_TENPO_FROM = re.compile(r"tenpo\.cl", re.IGNORECASE)

_RE_AMOUNT_COMPRA = re.compile(r"Monto\s+transacci[oó]n:\s*\$?\s*([\d\.]+)", re.IGNORECASE)
_RE_AMOUNT_TRANSFER = re.compile(r"Monto\s+transferencia:\s*\$?\s*([\d\.]+)", re.IGNORECASE)
_RE_COMERCIO = re.compile(r"Comercio:\s*([^\n]+)", re.IGNORECASE)
_RE_ORIGEN = re.compile(r"Origen\s+transferencia:\s*([^\n]+)", re.IGNORECASE)
_RE_FECHA = re.compile(r"Fecha:\s*(\d{2}-\d{2}-\d{4})")
_RE_HORA = re.compile(r"Hora:\s*(\d{2}:\d{2}:\d{2})")


def _parse_clp(raw: str) -> Decimal | None:
    """Remove thousands dots and parse as integer pesos."""
    cleaned = raw.replace(".", "").replace(",", "").strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_datetime(body: str) -> datetime | None:
    date_m = _RE_FECHA.search(body)
    time_m = _RE_HORA.search(body)
    if not date_m:
        return None
    time_str = time_m.group(1) if time_m else "00:00:00"
    try:
        return datetime.strptime(f"{date_m.group(1)} {time_str}", "%d-%m-%Y %H:%M:%S")
    except ValueError:
        return None


class TenpoParser(BaseParser):
    def can_parse(self, email_data: dict) -> bool:
        from_addr = email_data.get("from", "")
        subject = email_data.get("subject", "")
        return bool(
            _TENPO_FROM.search(from_addr) or "tenpo" in subject.lower()
        )

    def parse(self, email_data: dict) -> ParsedTransaction | None:
        body = email_data.get("body_plain", "")
        subject = email_data.get("subject", "")
        message_id = email_data.get("message_id", "")

        if _is_compra(body, subject):
            return self._parse_compra(body, subject, message_id)
        if _is_transferencia_recibida(body, subject):
            return self._parse_transferencia(body, subject, message_id)
        if _is_pago_tarjeta(body, subject):
            return self._parse_pago_tarjeta(body, subject, message_id)
        return None

    def _parse_compra(self, body: str, subject: str, message_id: str) -> ParsedTransaction | None:
        amount_m = _RE_AMOUNT_COMPRA.search(body)
        merchant_m = _RE_COMERCIO.search(body)
        if not amount_m or not merchant_m:
            return None
        amount = _parse_clp(amount_m.group(1))
        if amount is None:
            return None
        dt = _parse_datetime(body) or datetime.utcnow()
        return ParsedTransaction(
            amount=amount,
            merchant=merchant_m.group(1).strip(),
            transaction_date=dt,
            transaction_type="expense",
            source="tenpo",
            source_email_id=message_id,
            raw_subject=subject,
        )

    def _parse_transferencia(
        self, body: str, subject: str, message_id: str
    ) -> ParsedTransaction | None:
        amount_m = _RE_AMOUNT_TRANSFER.search(body)
        if not amount_m:
            return None
        amount = _parse_clp(amount_m.group(1))
        if amount is None:
            return None
        origen_m = _RE_ORIGEN.search(body)
        merchant = origen_m.group(1).strip() if origen_m else "Transferencia recibida"
        dt = _parse_datetime(body) or datetime.utcnow()
        return ParsedTransaction(
            amount=amount,
            merchant=merchant,
            transaction_date=dt,
            transaction_type="income",
            source="tenpo",
            source_email_id=message_id,
            raw_subject=subject,
        )

    def _parse_pago_tarjeta(
        self, body: str, subject: str, message_id: str
    ) -> ParsedTransaction | None:
        amount_m = _RE_AMOUNT_COMPRA.search(body)
        if not amount_m:
            return None
        amount = _parse_clp(amount_m.group(1))
        if amount is None:
            return None
        dt = _parse_datetime(body) or datetime.utcnow()
        return ParsedTransaction(
            amount=amount,
            merchant="TENPO CREDITO",
            transaction_date=dt,
            transaction_type="expense",
            source="tenpo",
            source_email_id=message_id,
            raw_subject=subject,
        )


def _is_compra(body: str, subject: str) -> bool:
    return "Comprobante de Compra exitosa" in body or "comprobante de compra" in subject.lower()


def _is_transferencia_recibida(body: str, subject: str) -> bool:
    return "Comprobante de recibo transferencia" in body or (
        "transferencia" in subject.lower() and "tenpo" in subject.lower()
    )


def _is_pago_tarjeta(body: str, subject: str) -> bool:
    return "Comprobante pago de tarjeta" in body or "pago de tu Tarjeta de" in subject
