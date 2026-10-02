"""Printer plugin interfaces and registry.

Printers are optional: the application always has a text ticket fallback and
does not import hardware-specific libraries unless a plugin is registered.
"""
from .base import Printer, PrinterRegistry, TextPrinter
from .escpos import EscPosPrinter

registry = PrinterRegistry()
registry.register("text", TextPrinter())

__all__ = ["Printer", "PrinterRegistry", "TextPrinter", "EscPosPrinter", "registry"]
