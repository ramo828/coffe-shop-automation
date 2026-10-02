"""Optional ESC/POS network or USB printer implementation.

No hardware dependency is required until this plugin is instantiated.
"""
import socket

from .base import Printer


class EscPosPrinter(Printer):
    def __init__(self, host=None, port=9100, usb_path=None, timeout=3):
        if not host and not usb_path:
            raise ValueError("host or usb_path is required")
        self.host = host
        self.port = int(port)
        self.usb_path = usb_path
        self.timeout = timeout

    def print_ticket(self, ticket: str) -> bool:
        payload = ticket.encode("utf-8", errors="replace") + b"\n\n\x1dV\x00"
        if self.usb_path:
            with open(self.usb_path, "ab", buffering=0) as device:
                device.write(payload)
            return True
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as connection:
            connection.sendall(payload)
        return True
