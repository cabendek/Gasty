from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class ParsedTransaction:
    amount: Decimal
    merchant: str
    transaction_date: datetime
    transaction_type: str
    source: str
    source_email_id: str
    raw_subject: str


class BaseParser(ABC):
    @abstractmethod
    def can_parse(self, email_data: dict) -> bool:
        pass

    @abstractmethod
    def parse(self, email_data: dict) -> ParsedTransaction | None:
        pass
