from dataclasses import replace
from decimal import Decimal, ROUND_FLOOR
from typing import Callable, Dict, List, Optional, Tuple

from allocation.models import AllocationResult, FacilityNeed
from allocation.need import is_allocatable
from allocation.uom import apply_uom_and_limits, max_acceptable, remaining_shortage

PolicyRawFn = Callable[[Decimal, List[FacilityNeed]], Dict[str, Decimal]]

POLICY_KEYS = (
    "proportional",
    "fixed_priority",
    "largest_shortage",
    "weighted_score",
)

DEFAULT_SHORTAGE_WEIGHT = Decimal("0.7")
DEFAULT_PRIORITY_WEIGHT = Decimal("0.3")


def _eligible(needs: List[FacilityNeed]) -> List[FacilityNeed]:
    return [n for n in needs if is_allocatable(n)]


def needs_with_remaining(
    needs: List[FacilityNeed],
    prior_allocations: Dict[str, Decimal],
) -> List[FacilityNeed]:
    """Build remainder-pass needs using unfilled gap after prior allocations (e.g. pallet crossdock)."""
    adjusted: List[FacilityNeed] = []
    for n in needs:
        prior = prior_allocations.get(n.facility_id, Decimal("0"))
        rem = remaining_shortage(n, prior)
        adjusted.append(
            replace(
                n,
                shortage=rem,
            )
        )
    return adjusted


def proportional_raw(asn_qty: Decimal, needs: List[FacilityNeed]) -> Dict[str, Decimal]:
    eligible = _eligible(needs)
    total = sum(n.shortage for n in eligible)
    if total <= 0 or asn_qty <= 0:
        return {}
    remaining = asn_qty
    allocations: Dict[str, Decimal] = {}
    for i, n in enumerate(eligible):
        if i == len(eligible) - 1:
            qty = remaining
        else:
            qty = (asn_qty * n.shortage / total).to_integral_value(rounding=ROUND_FLOOR)
        qty = min(qty, max_acceptable(n), remaining)
        if qty > 0:
            allocations[n.facility_id] = qty
            remaining -= qty
    return allocations


def fixed_priority_raw(asn_qty: Decimal, needs: List[FacilityNeed]) -> Dict[str, Decimal]:
    eligible = sorted(_eligible(needs), key=lambda n: n.priority)
    remaining = asn_qty
    allocations: Dict[str, Decimal] = {}
    for n in eligible:
        if remaining <= 0:
            break
        qty = min(n.shortage, remaining)
        if qty > 0:
            allocations[n.facility_id] = qty
            remaining -= qty
    return allocations


def largest_shortage_raw(asn_qty: Decimal, needs: List[FacilityNeed]) -> Dict[str, Decimal]:
    eligible = sorted(_eligible(needs), key=lambda n: n.shortage, reverse=True)
    remaining = asn_qty
    allocations: Dict[str, Decimal] = {}
    for n in eligible:
        if remaining <= 0:
            break
        qty = min(n.shortage, remaining)
        if qty > 0:
            allocations[n.facility_id] = qty
            remaining -= qty
    return allocations


def _facility_scores(
    needs: List[FacilityNeed],
    shortage_weight: Decimal = DEFAULT_SHORTAGE_WEIGHT,
    priority_weight: Decimal = DEFAULT_PRIORITY_WEIGHT,
) -> List[Tuple[Decimal, FacilityNeed]]:
    eligible = _eligible(needs)
    if not eligible:
        return []
    max_shortage = max(n.shortage for n in eligible)
    max_priority = max(n.priority for n in eligible)
    scored: List[Tuple[Decimal, FacilityNeed]] = []
    for n in eligible:
        shortage_norm = n.shortage / max_shortage if max_shortage > 0 else Decimal("0")
        priority_norm = Decimal(max_priority - n.priority + 1) / Decimal(max_priority)
        score = shortage_weight * shortage_norm + priority_weight * priority_norm
        scored.append((score, n))
    return scored


def weighted_score_raw(
    asn_qty: Decimal,
    needs: List[FacilityNeed],
    shortage_weight: Decimal = DEFAULT_SHORTAGE_WEIGHT,
    priority_weight: Decimal = DEFAULT_PRIORITY_WEIGHT,
) -> Dict[str, Decimal]:
    """Fill facilities in blended score order (default 70% shortage + 30% priority)."""
    scored = sorted(
        _facility_scores(needs, shortage_weight, priority_weight),
        key=lambda item: item[0],
        reverse=True,
    )
    remaining = asn_qty
    allocations: Dict[str, Decimal] = {}
    for _score, n in scored:
        if remaining <= 0:
            break
        qty = min(n.shortage, remaining)
        if qty > 0:
            allocations[n.facility_id] = qty
            remaining -= qty
    return allocations


POLICY_RAW: Dict[str, PolicyRawFn] = {
    "proportional": proportional_raw,
    "fixed_priority": fixed_priority_raw,
    "largest_shortage": largest_shortage_raw,
    "weighted_score": weighted_score_raw,
}


def full_pallet_raw(
    asn_qty: Decimal,
    needs: List[FacilityNeed],
) -> Tuple[Dict[str, Decimal], Decimal, List[dict]]:
    eligible = _eligible(needs)
    crossdock: List[dict] = []
    allocations: Dict[str, Decimal] = {}
    remaining = asn_qty

    for n in sorted(eligible, key=lambda x: x.shortage, reverse=True):
        pallet = n.pallet_qty
        if pallet <= 0 or remaining < pallet:
            continue
        if n.shortage >= pallet:
            pallets_to_assign = min(
                (remaining / pallet).to_integral_value(rounding=ROUND_FLOOR),
                (n.shortage / pallet).to_integral_value(rounding=ROUND_FLOOR),
            )
            if pallets_to_assign <= 0:
                continue
            qty = pallets_to_assign * pallet
            allocations[n.facility_id] = allocations.get(n.facility_id, Decimal("0")) + qty
            remaining -= qty
            crossdock.append(
                {
                    "facility_id": n.facility_id,
                    "quantity": str(qty),
                    "handling_unit": "pallet",
                    "pallet_qty": str(pallet),
                    "recommendation": "crossdock",
                }
            )
            break

    return allocations, remaining, crossdock


def run_policy(
    asn_qty: Decimal,
    needs: List[FacilityNeed],
    policy_key: str,
    *,
    display_name: Optional[str] = None,
) -> AllocationResult:
    """
    Pallet crossdock pass (when applicable), remainder split by policy using
    remaining need after crossdock, then pack rounding and residual sweep.
    """
    if policy_key not in POLICY_RAW:
        raise ValueError(f"Unknown policy: {policy_key}")

    pallet_alloc, loose_qty, crossdock = full_pallet_raw(asn_qty, needs)
    allocations: Dict[str, Decimal] = dict(pallet_alloc)
    notes: List[str] = []

    if loose_qty > 0:
        remainder_needs = needs_with_remaining(needs, pallet_alloc) if pallet_alloc else needs
        extra = POLICY_RAW[policy_key](loose_qty, remainder_needs)
        for fid, qty in extra.items():
            allocations[fid] = allocations.get(fid, Decimal("0")) + qty

    final, residual, uom_notes = apply_uom_and_limits(allocations, needs, asn_qty)
    notes.extend(uom_notes)

    if policy_key == "weighted_score":
        notes.insert(0, "Rank by score (70% shortage + 30% priority), fill in order")
    if pallet_alloc:
        notes.insert(0, "Remainder pass uses remaining need after pallet crossdock")

    return AllocationResult(
        algorithm=display_name or policy_key,
        allocations=final,
        residual_qty=residual,
        crossdock_recommendations=crossdock,
        notes=notes,
    )


POLICY_LABELS = {
    "proportional": "Proportional",
    "fixed_priority": "Fixed Pty",
    "largest_shortage": "Largest",
    "weighted_score": "Weighted",
}

COMPARISON_COLUMNS = [
    ("proportional", "1 Proportional"),
    ("fixed_priority", "2 Fixed Pty"),
    ("largest_shortage", "3 Largest"),
    ("weighted_score", "4 Weighted"),
    ("default", "5 Default"),
]

# Backward-compatible aliases for engine imports
ALGORITHMS = {key: (lambda k: lambda q, n: run_policy(q, n, k))(key) for key in POLICY_KEYS}
ALGORITHM_LABELS = COMPARISON_COLUMNS
