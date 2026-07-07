"""Capture allocation steps for human-readable explanations."""

from decimal import Decimal
from typing import Dict, List, Optional

from allocation.models import FacilityNeed
from allocation.need import is_allocatable


def _fq(qty) -> str:
    if qty in (None, ""):
        return "0"
    d = Decimal(str(qty))
    if d == d.to_integral_value():
        return str(int(d))
    return str(d.normalize())


def facility_snapshots(needs: List[FacilityNeed]) -> List[dict]:
    rows = []
    for n in needs:
        rows.append(
            {
                "suffix": n.facility_suffix,
                "facility_id": n.facility_id,
                "priority": n.priority,
                "shortage": _fq(n.shortage),
                "max_qty": _fq(n.max_qty),
                "position": _fq(n.inventory_position),
                "allocatable": is_allocatable(n),
            }
        )
    return rows


def remainder_snapshots(needs: List[FacilityNeed]) -> List[dict]:
    return [
        {
            "suffix": n.facility_suffix,
            "remaining_need": _fq(n.shortage),
            "priority": n.priority,
        }
        for n in needs
        if is_allocatable(n)
    ]


def allocations_by_suffix(
    allocations: Dict[str, Decimal], needs: List[FacilityNeed]
) -> Dict[str, str]:
    fid_to_suffix = {n.facility_id: n.facility_suffix for n in needs}
    out: Dict[str, str] = {}
    for fid, qty in allocations.items():
        suffix = fid_to_suffix.get(fid)
        if suffix and qty > 0:
            out[suffix] = _fq(qty)
    return out
