from decimal import Decimal
from typing import Dict, List, Optional

from allocation.models import FacilityNeed, PartParams


def is_allocatable(n: FacilityNeed) -> bool:
    """Facility participates when it carries the item (max > 0) and has unfilled need."""
    return n.max_qty > 0 and n.shortage > 0


def resolve_facility(org: str, suffix: str) -> str:
    org = org.upper()
    suffix = suffix.upper()
    if suffix.startswith(org):
        return suffix
    return f"{org}-{suffix}"


def build_facility_needs(
    org: str,
    item_id: str,
    facilities: List[dict],
    facility_parts: List[dict],
    part_params: Optional[PartParams],
    item_pack_qty: Optional[Decimal] = None,
    item_pallet_qty: Optional[Decimal] = None,
) -> List[FacilityNeed]:
    part_rows = [fp for fp in facility_parts if fp["item_id"] == item_id]
    facility_lookup = {f["facility_id"]: f for f in facilities if f.get("active", True)}
    needs: List[FacilityNeed] = []

    pack_qty = Decimal("0")
    pallet_qty = Decimal("0")
    allow_split = False
    over_max = Decimal("0")
    if part_params:
        if part_params.pack_qty:
            pack_qty = part_params.pack_qty
        if part_params.pallet_qty:
            pallet_qty = part_params.pallet_qty
        allow_split = part_params.allow_split_pack
        over_max = part_params.over_max_tolerance
    if pack_qty <= 0 and item_pack_qty and item_pack_qty > 0:
        pack_qty = item_pack_qty
    if pallet_qty <= 0 and item_pallet_qty and item_pallet_qty > 0:
        pallet_qty = item_pallet_qty

    for suffix, fac in sorted(facility_lookup.items(), key=lambda x: x[1].get("priority", 999)):
        fp = next((row for row in part_rows if row["facility_id"] == suffix), None)
        if not fp:
            continue
        available = Decimal(str(fp.get("available_qty", 0)))
        inbound = Decimal(str(fp.get("inbound_qty", 0)))
        outbound = Decimal(str(fp.get("outbound_qty", 0)))
        max_qty = Decimal(str(fp.get("max_qty", 0)))
        position = available + inbound - outbound
        shortage = max_qty - position
        if shortage < 0:
            shortage = Decimal("0")

        fp_pack = fp.get("pack_qty")
        fp_pallet = fp.get("pallet_qty")
        row_pack = Decimal(str(fp_pack)) if fp_pack not in (None, "") else pack_qty
        row_pallet = Decimal(str(fp_pallet)) if fp_pallet not in (None, "") else pallet_qty

        needs.append(
            FacilityNeed(
                facility_suffix=suffix,
                facility_id=resolve_facility(org, suffix),
                priority=int(fac.get("priority", 999)),
                item_id=item_id,
                max_qty=max_qty,
                available_qty=available,
                inbound_qty=inbound,
                outbound_qty=outbound,
                inventory_position=position,
                shortage=shortage,
                pack_qty=row_pack,
                pallet_qty=row_pallet,
                allow_split_pack=allow_split,
                over_max_tolerance=over_max,
            )
        )
    return needs


def needs_summary(needs: List[FacilityNeed]) -> List[dict]:
    return [
        {
            "facility_id": n.facility_id,
            "facility_suffix": n.facility_suffix,
            "priority": n.priority,
            "inventory_position": str(n.inventory_position),
            "shortage": str(n.shortage),
            "max_qty": str(n.max_qty),
            "available_qty": str(n.available_qty),
            "inbound_qty": str(n.inbound_qty),
            "outbound_qty": str(n.outbound_qty),
        }
        for n in needs
    ]
