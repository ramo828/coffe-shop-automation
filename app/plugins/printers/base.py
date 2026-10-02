from abc import ABC, abstractmethod


class Printer(ABC):
    @abstractmethod
    def print_ticket(self, ticket: str) -> bool:
        """Print a ticket and return whether it was accepted."""


class TextPrinter(Printer):
    def __init__(self, sink=None):
        self.sink = sink

    def print_ticket(self, ticket):
        if self.sink:
            self.sink(ticket)
        return True


class PrinterRegistry:
    def __init__(self):
        self._printers = {}

    def register(self, name, printer):
        if not name or not isinstance(printer, Printer):
            raise TypeError("name and Printer instance are required")
        self._printers[str(name)] = printer

    def get(self, name="text"):
        return self._printers.get(name) or self._printers["text"]

    def names(self):
        return sorted(self._printers)
