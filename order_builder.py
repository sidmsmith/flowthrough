"""Build facility-level replenishment orders from per-ASN-line allocations."""

from collections import defaultdict
from decimal import Decimal
from typing import Dict, List


def facility_suffix(facility_id: str) -> str:
    """SS-DEMO-DM2 → DM2."""
    return facility_id.split("-")[-1]


def build_order_id(asn_id: str, destination_facility_id: str) -> str:
    return f"FLOW-{asn_id}-{facility_suffix(destination_facility_id)}"


def accumulate_line_allocations(
    facility_orders: Dict[str, List[dict]],
    item_id: str,
    uom: str,
    allocations: Dict[str, Decimal],
) -> None:
    """Append one order-line candidate per destination for a single ASN line."""
    for dest, qty in allocations.items():
        qty = Decimal(str(qty))
        if qty <= 0:
            continue
        facility_orders[dest].append(
            {
                "item_id": item_id,
                "uom": uom or "UNIT",
                "quantity": qty,
            }
        )


def new_facility_order_buckets() -> Dict[str, List[dict]]:
    return defaultdict(list)


def renumber_order_lines(facility_orders: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    """
    Ensure each facility order has sequential OrderLineId values 1..n.
    Returns a plain dict (preserves facility insertion order).
    """
    renumbered: Dict[str, List[dict]] = {}
    for dest, lines in facility_orders.items():
        renumbered[dest] = [
            {
                "order_line_id": str(i),
                "item_id": line["item_id"],
                "uom": line["uom"],
                "quantity": line["quantity"],
            }
            for i, line in enumerate(lines, start=1)
        ]
    return renumbered
