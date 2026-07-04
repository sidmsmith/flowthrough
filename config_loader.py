import json
from pathlib import Path
from typing import Optional


def load_config(path: Optional[str] = None) -> dict:
    if path is None:
        path = Path(__file__).parent / "data" / "facility_inventory.json"
    else:
        path = Path(path)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_asn_definitions(path: Optional[str] = None) -> dict:
    if path is None:
        path = Path(__file__).parent / "data" / "postman_asns.json"
    else:
        path = Path(path)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def resolve_facility(org: str, suffix: str) -> str:
    org = org.upper()
    suffix = suffix.upper()
    if suffix.startswith(org):
        return suffix
    return f"{org}-{suffix}"


def receiving_facility_id(org: str, config: dict) -> str:
    suffix = config.get("receiving_facility", "DM1")
    return resolve_facility(org, suffix)
