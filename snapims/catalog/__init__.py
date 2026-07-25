"""Permanent local movie catalog for SnapIMS.

SLMC keeps film-level facts in a separate SQLite database. The inventory database
remains authoritative for physical Items and batches.
"""

from snapims.catalog.db import CATALOG_SCHEMA_VERSION

SLMC_VERSION = "SLMC-0.1.0"

__all__ = ["CATALOG_SCHEMA_VERSION", "SLMC_VERSION"]
