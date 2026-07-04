from decimal import Decimal
from typing import List, Optional

from allocation.algorithms import (
    COMPARISON_COLUMNS,
    POLICY_KEYS,
    POLICY_LABELS,
    run_policy,
)
from allocation.models import AllocationResult, FacilityNeed, PartParams
from allocation.need import build_facility_needs

LEGACY_DEFAULT_ALGORITHMS = {
    "hybrid": "proportional",
    "full_pallet": "proportional",
    "best": "proportional",
}

NUMERIC_POLICY = {
    "1": "proportional",
    "2": "fixed_priority",
    "3": "largest_shortage",
    "4": "weighted_score",
}


def resolve_default_algorithm(part: Optional[PartParams], config: dict) -> str:
    raw = None
    if part and part.default_algorithm:
        raw = part.default_algorithm.strip().lower()
    if not raw:
        raw = (config.get("default_algorithm") or "proportional").strip().lower()
    raw = LEGACY_DEFAULT_ALGORITHMS.get(raw, raw)
    raw = NUMERIC_POLICY.get(raw, raw)
    if raw not in POLICY_KEYS:
        return "proportional"
    return raw


def default_column_label(default_key: str) -> str:
    name = POLICY_LABELS.get(default_key, default_key)
    return f"5 Default ({name})"


def _load_parts(config: dict) -> dict[str, PartParams]:
    return {p["item_id"]: PartParams(**_part_kwargs(p)) for p in config.get("parts", [])}


def _build_needs(
    org: str,
    item_id: str,
    config: dict,
    part: Optional[PartParams],
    item_pack_qty=None,
    item_pallet_qty=None,
) -> List[FacilityNeed]:
    return build_facility_needs(
        org,
        item_id,
        config.get("facilities", []),
        config.get("facility_parts", []),
        part,
        item_pack_qty=item_pack_qty,
        item_pallet_qty=item_pallet_qty,
    )


def run_algorithm(
    name: str,
    asn_qty: Decimal,
    org: str,
    item_id: str,
    config: dict,
    item_pack_qty=None,
    item_pallet_qty=None,
) -> AllocationResult:
    parts = _load_parts(config)
    part = parts.get(item_id)
    needs = _build_needs(org, item_id, config, part, item_pack_qty, item_pallet_qty)
    key = resolve_default_algorithm(part, config) if name in ("default", "best") else name
    key = LEGACY_DEFAULT_ALGORITHMS.get(key, key)
    key = NUMERIC_POLICY.get(key, key)
    if key not in POLICY_KEYS:
        raise ValueError(f"Unknown algorithm: {name}")
    display = f"default ({key})" if name in ("default", "best") else None
    return run_policy(asn_qty, needs, key, display_name=display)


def run_all_algorithms(
    asn_qty: Decimal,
    org: str,
    item_id: str,
    config: dict,
    item_pack_qty=None,
    item_pallet_qty=None,
) -> tuple[List[FacilityNeed], dict[str, AllocationResult], str]:
    parts = _load_parts(config)
    part = parts.get(item_id)
    needs = _build_needs(org, item_id, config, part, item_pack_qty, item_pallet_qty)
    default_key = resolve_default_algorithm(part, config)

    results: dict[str, AllocationResult] = {}
    for key in POLICY_KEYS:
        results[key] = run_policy(asn_qty, needs, key)

    default_result = run_policy(
        asn_qty,
        needs,
        default_key,
        display_name=f"default ({default_key})",
    )
    results["default"] = default_result

    return needs, results, default_key


def _part_kwargs(p: dict) -> dict:
    return {
        "item_id": p["item_id"],
        "pack_qty": _dec_or_none(p.get("pack_qty")),
        "pallet_qty": _dec_or_none(p.get("pallet_qty")),
        "allow_split_pack": bool(p.get("allow_split_pack", False)),
        "crossdock_preference": p.get("crossdock_preference", "full_pallet_first"),
        "min_order_qty": Decimal(str(p.get("min_order_qty", 1))),
        "over_max_tolerance": Decimal(str(p.get("over_max_tolerance", 0))),
        "default_algorithm": p.get("default_algorithm"),
    }


def _dec_or_none(value):
    if value in (None, ""):
        return None
    return Decimal(str(value))
