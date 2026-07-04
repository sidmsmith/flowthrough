from decimal import Decimal, ROUND_FLOOR
from typing import Dict, List, Tuple

from allocation.models import AllocationResult, FacilityNeed
from allocation.need import is_allocatable


def floor_to_pack(qty: Decimal, pack_qty: Decimal, allow_split: bool) -> Decimal:
    if pack_qty <= 0:
        return qty
    if allow_split:
        return qty
    packs = (qty / pack_qty).to_integral_value(rounding=ROUND_FLOOR)
    return packs * pack_qty


def round_to_valid_pack(qty: Decimal, n: FacilityNeed) -> Decimal:
    """Floor to full packs; round up to one pack when tolerance allows a full pack."""
    if qty <= 0:
        return Decimal("0")
    if n.pack_qty <= 0 or n.allow_split_pack:
        return min(qty, max_acceptable(n))
    rounded = floor_to_pack(qty, n.pack_qty, False)
    if rounded > 0:
        return min(rounded, max_acceptable(n))
    limit = max_acceptable(n)
    if limit >= n.pack_qty:
        return n.pack_qty
    return Decimal("0")


def max_acceptable(n: FacilityNeed) -> Decimal:
    headroom = n.max_qty + n.over_max_tolerance - n.inventory_position
    if headroom < 0:
        return Decimal("0")
    limit = n.shortage + n.over_max_tolerance if n.over_max_tolerance > 0 else n.shortage
    return min(limit, headroom)


def remaining_shortage(n: FacilityNeed, allocated: Decimal) -> Decimal:
    """Units still needed to reach shortage (ignores over-max tolerance band)."""
    return max(Decimal("0"), n.shortage - allocated)


def headroom(n: FacilityNeed, allocated: Decimal) -> Decimal:
    return max(Decimal("0"), max_acceptable(n) - allocated)


def sweep_residual(
    allocations: Dict[str, Decimal],
    residual: Decimal,
    needs: List[FacilityNeed],
) -> Tuple[Dict[str, Decimal], Decimal, List[str]]:
    """
    Assign leftover ASN qty to facilities that carry the item (`max_qty > 0`) and still need inventory.
    Prefers facilities with the largest unmet shortage; respects pack size and max/tolerance.
    """
    notes: List[str] = []
    need_map = {n.facility_id: n for n in needs if n.max_qty > 0}
    result = dict(allocations)

    while residual > 0:
        best = None
        for fid, n in need_map.items():
            current = result.get(fid, Decimal("0"))
            room = headroom(n, current)
            if room <= 0:
                continue

            if n.pack_qty > 0 and not n.allow_split_pack:
                if residual < n.pack_qty or room < n.pack_qty:
                    continue
                increment = n.pack_qty
            else:
                increment = min(residual, room)

            if increment <= 0:
                continue

            need_gap = remaining_shortage(n, current)
            score = (need_gap > 0, need_gap, room)
            if best is None or score > best[0]:
                best = (score, fid, increment)

        if best is None:
            break

        _, fid, increment = best
        result[fid] = result.get(fid, Decimal("0")) + increment
        residual -= increment
        notes.append(f"{fid}: +{increment} residual sweep")

    return result, residual, notes


def apply_uom_and_limits(
    raw: Dict[str, Decimal],
    needs: List[FacilityNeed],
    asn_qty: Decimal,
    sweep: bool = True,
) -> Tuple[Dict[str, Decimal], Decimal, List[str]]:
    need_map = {n.facility_id: n for n in needs if n.max_qty > 0}
    notes: List[str] = []
    result: Dict[str, Decimal] = {}

    for facility_id, qty in raw.items():
        n = need_map.get(facility_id)
        if not n or qty <= 0:
            continue
        capped = min(qty, max_acceptable(n))
        rounded = round_to_valid_pack(capped, n)
        if rounded <= 0:
            notes.append(f"{facility_id}: {qty} could not be rounded to valid pack")
            continue
        if rounded > 0:
            result[facility_id] = rounded

    allocated = sum(result.values(), Decimal("0"))
    residual = asn_qty - allocated
    if residual < 0:
        residual = Decimal("0")

    result, residual, sweep_notes = (
        sweep_residual(result, residual, needs) if sweep else (result, residual, [])
    )
    notes.extend(sweep_notes)
    return result, residual, notes
