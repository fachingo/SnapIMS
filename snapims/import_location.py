from __future__ import annotations

import hashlib

from snapims.protocol import CommandKind, parse_command


class ImportLocationError(ValueError):
    """Raised when a manual Import location assignment is invalid."""


def normalize_manual_location(
    value: object,
    override_locations: bool = False,
) -> tuple[str, bool]:
    """Return one validated shelf and a safe override flag.

    An empty location is valid only when override mode is off.  Location rules
    intentionally reuse the QR protocol parser so manual and QR assignments can
    never drift apart.
    """

    location = str(value or "").strip().upper()
    override = bool(override_locations)
    if not location:
        if override:
            raise ImportLocationError(
                "Enter a manual location before selecting Override all location QR cards."
            )
        return "", False
    command = parse_command(f"CVHS1:LOC:{location}")
    if command is None or command.kind != CommandKind.LOCATION:
        raise ImportLocationError(
            "Manual location must be Q1 or A1 through J10 (for example, A6)."
        )
    return str(command.value or ""), override


def location_assignment_fingerprint(
    base_fingerprint: str,
    manual_location: object,
    override_locations: bool = False,
) -> str:
    """Bind a location assignment to duplicate detection and import identity."""

    location, override = normalize_manual_location(
        manual_location,
        override_locations,
    )
    if not location:
        return base_fingerprint
    digest = hashlib.sha256()
    digest.update(base_fingerprint.encode("ascii"))
    digest.update(b"\0manual-batch-location\0")
    digest.update(location.encode("ascii"))
    digest.update(b"\0override-all\0" if override else b"\0starting-location\0")
    return digest.hexdigest()


def location_assignment_warning(
    manual_location: object,
    override_locations: bool = False,
) -> str:
    location, override = normalize_manual_location(
        manual_location,
        override_locations,
    )
    if not location:
        return ""
    if override:
        return (
            f"Manual batch location {location} overrides LOCATION QR cards; "
            f"every item uses {location}."
        )
    return (
        f"Manual batch location {location} assigned as the starting location; "
        "later valid LOCATION QR cards may change it."
    )
