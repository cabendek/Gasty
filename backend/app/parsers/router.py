from app.parsers.base import BaseParser, ParsedTransaction
from app.parsers.tenpo import TenpoParser

_PARSERS: list[BaseParser] = [TenpoParser()]


def parser_router(email_data: dict) -> ParsedTransaction | None:
    for parser in _PARSERS:
        if parser.can_parse(email_data):
            return parser.parse(email_data)
    return None
