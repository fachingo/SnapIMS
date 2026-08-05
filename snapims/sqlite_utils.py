"""Small SQLite safety helpers shared by SnapIMS subsystems."""

from __future__ import annotations

import sqlite3


class ClosingConnection(sqlite3.Connection):
    """Commit/rollback on context exit and always release the OS handle."""

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc, traceback))
        finally:
            self.close()
