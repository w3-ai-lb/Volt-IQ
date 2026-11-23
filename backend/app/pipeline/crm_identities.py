"""
Read the identity layer out of the CRM project's own seed file.

    data/crm/customer_side_seed_data.sql

WHAT THIS FILE IS
-----------------
The customer-side half of the project runs on Supabase, with its own schema:
zones, generators, employees, subscribers, subscriptions, meters, tariffs,
meter_readings, invoices, payments, all keyed by UUID and guarded by row-level
security. Its seed file is that schema populated, and it is the shape the
supervisor asked the subscriber and meter data to match.

It also reuses the same twelve zone names and the same seven generator names
as the analytics dataset, deliberately, so both halves describe one site. That
has been verified rather than assumed: all twelve and all seven match exactly.

WHAT IS TAKEN FROM IT, AND WHAT IS NOT
--------------------------------------
TAKEN: the identity layer, which the analytics dataset does not have at all:
forty-five people with a name, a phone, a street address and a coordinate, and
the conventions behind them, so records generated for the remaining subscribers
are indistinguishable in style from the ones the CRM already holds.

NOT TAKEN: its 586 meter readings, 598 invoices, 536 payments and 12 tariffs.
Those describe the same twelve zones over September 2025 to August 2026, while
the supervisor's own export describes them over January 2025 to June 2026. They
are two different accounts of one place. Loading both would put two energy
totals behind a single zone and produce a loss figure that is the sum of two
unrelated worlds, and every number in the report so far comes from his export.

So: his measurements, its names.

A NOTE ON THE COORDINATES
-------------------------
They are not surveyed. In the source file the points are scattered across Mount
Lebanon with no relation to the zone the subscriber belongs to: four Harjali
subscribers sit up to twenty kilometres apart. They are carried because the CRM
record shape carries them, and for no other reason. See Customer.gps_lat.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# data/crm/customer_side_seed_data.sql, relative to the backend root.
SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "crm" / "customer_side_seed_data.sql"

# One subscriber row: id, name, phone, address, zone id, lat, lng, active.
_SUBSCRIBER = re.compile(
    r"\('([0-9a-f-]{36})',\s*'([^']+)',\s*'(\d{8})',\s*'([^']+)',\s*"
    r"'([0-9a-f-]{36})',\s*([-\d.]+),\s*([-\d.]+),\s*(TRUE|FALSE)\)"
)
_ZONE = re.compile(r"\('([0-9a-f-]{36})',\s*'([^']+)',\s*'(?:rural|urban)',\s*(?:TRUE|FALSE)\)")

# The address the CRM writes. Rebuilt for generated records so the two sets of
# rows cannot be told apart by their formatting.
ADDRESS_FORMAT = "Bldg {building}, {zone} main road, {zone}"

# Lebanese mobile prefixes, exactly the six the CRM file uses.
PHONE_PREFIXES = ("03", "70", "71", "76", "78", "81")


@dataclass(frozen=True)
class Identity:
    """One person as the CRM records them."""

    name: str
    phone: str
    address: str
    zone_name: str
    gps_lat: float
    gps_lng: float
    is_active: bool


@dataclass(frozen=True)
class CrmSeed:
    """Everything this module knows, after reading the file once."""

    identities: tuple[Identity, ...]
    first_names: tuple[str, ...]
    family_names: tuple[str, ...]
    lat_range: tuple[float, float]
    lng_range: tuple[float, float]

    @property
    def available(self) -> bool:
        return bool(self.identities)


# If the file is absent the pipeline must still run: the names below are the
# ones parsed out of it, kept here so a missing file degrades to the same style
# rather than to an error. They are not a second invented list.
_FALLBACK_FIRST = (
    "Ahmad", "Ali", "Antoine", "Bilal", "Christelle", "Dima", "Elie", "Fadi",
    "Fatima", "Georges", "Hala", "Hassan", "Joelle", "Karim", "Khaled", "Lina",
    "Nabil", "Nada", "Nour", "Rabih", "Rania", "Rasha", "Reem", "Rita",
    "Talal", "Yara", "Zeinab", "Ziad",
)
_FALLBACK_FAMILY = (
    "Abou Zeid", "Aoun", "Barakat", "Boustani", "Chami", "Chidiac", "Daher",
    "Fakhoury", "Ghosn", "Haddad", "Hamdan", "Kanaan", "Karam", "Khalil",
    "Matar", "Nassar", "Rahal", "Salame", "Sarkis", "Traboulsi", "Younes",
    "Zeidan",
)
_FALLBACK_LAT = (33.6963, 33.9587)
_FALLBACK_LNG = (35.4363, 35.7213)


def load(path: Path | None = None) -> CrmSeed:
    """Parse the CRM seed. Returns an empty-but-usable seed if it is missing."""
    source = path or SEED_PATH
    if not source.exists():
        return CrmSeed(
            identities=(),
            first_names=_FALLBACK_FIRST,
            family_names=_FALLBACK_FAMILY,
            lat_range=_FALLBACK_LAT,
            lng_range=_FALLBACK_LNG,
        )

    text = source.read_text(encoding="utf-8", errors="replace")
    zones = {uuid: name for uuid, name in _ZONE.findall(text)}

    identities: list[Identity] = []
    for uuid, name, phone, address, zone_uuid, lat, lng, active in _SUBSCRIBER.findall(text):
        identities.append(
            Identity(
                name=name,
                phone=phone,
                address=address,
                zone_name=zones.get(zone_uuid, ""),
                gps_lat=float(lat),
                gps_lng=float(lng),
                is_active=(active == "TRUE"),
            )
        )

    if not identities:
        return CrmSeed(
            identities=(),
            first_names=_FALLBACK_FIRST,
            family_names=_FALLBACK_FAMILY,
            lat_range=_FALLBACK_LAT,
            lng_range=_FALLBACK_LNG,
        )

    firsts, families = set(), set()
    for identity in identities:
        parts = identity.name.split()
        firsts.add(parts[0])
        families.add(" ".join(parts[1:]))

    lats = [i.gps_lat for i in identities]
    lngs = [i.gps_lng for i in identities]

    return CrmSeed(
        identities=tuple(identities),
        first_names=tuple(sorted(firsts)),
        family_names=tuple(sorted(families)),
        lat_range=(min(lats), max(lats)),
        lng_range=(min(lngs), max(lngs)),
    )
