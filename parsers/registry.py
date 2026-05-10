"""Parser registry — detects the correct parser for a given message."""
from __future__ import annotations

from typing import List, Optional, Tuple

from parsers.base import BaseParser, ParsedOrder
from parsers.site_parser import SiteParser
from parsers.app_parser import AppParser


class ParserRegistry:
    """Holds all registered parsers and dispatches to the best match."""

    def __init__(self) -> None:
        self._parsers: List[BaseParser] = []

    def register(self, parser: BaseParser) -> None:
        self._parsers.append(parser)
        self._parsers.sort(key=lambda p: p.priority, reverse=True)

    def detect_parser(self, text: str) -> Optional[BaseParser]:
        for parser in self._parsers:
            if parser.can_parse(text):
                return parser
        return None

    def parse(self, text: str) -> Tuple[Optional[ParsedOrder], Optional[str], Optional[str]]:
        """
        Returns (parsed_order, parser_name, error_message).
        error_message is set only on failure.
        """
        parser = self.detect_parser(text)
        if parser is None:
            return None, None, "Unknown message format — no matching parser"

        result, error = parser.safe_parse(text)
        return result, parser.name, error

    @property
    def parser_names(self) -> List[str]:
        return [p.name for p in self._parsers]


def build_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(SiteParser())
    registry.register(AppParser())
    return registry
