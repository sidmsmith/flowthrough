from dataclasses import replace
from decimal import Decimal, ROUND_FLOOR
from typing import Callable, Dict, List, Optional, Tuple

from allocation.models import AllocationResult, FacilityNeed
from allocation.need import is_allocatable
from allocation.trace_helpers import (
    allocations_by_suffix,
    facility_snapshots,
    remainder_snapshots,
    _fq,
)
from allocation.uom import apply_uom_and_limits, max_acceptable, remaining_shortage

PolicyRawFn = Callable[..., Dict[str, Decimal]]

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


def proportional_raw(
    asn_qty: Decimal,
    needs: List[FacilityNeed],
    *,
    steps: Optional[List[dict]] = None,
) -> Dict[str, Decimal]:
    eligible = _eligible(needs)
    total = sum(n.shortage for n in eligible)
    if total <= 0 or asn_qty <= 0:
        return {}
    remaining = asn_qty
    allocations: Dict[str, Decimal] = {}
    for i, n in enumerate(eligible):
        if i == len(eligible) - 1:
            qty = remaining
            share_pct = None
        else:
            qty = (asn_qty * n.shortage / total).to_integral_value(rounding=ROUND_FLOOR)
            share_pct = float((n.shortage / total) * 100)
        qty = min(qty, max_acceptable(n), remaining)
        if qty > 0:
            allocations[n.facility_id] = qty
            remaining -= qty
            if steps is not None:
                steps.append(
                    {
                        "type": "proportional_share",
                        "suffix": n.facility_suffix,
                        "share_pct": round(share_pct, 1) if share_pct is not None else None,
                        "qty": _fq(qty),
                        "remaining_need": _fq(n.shortage),
                    }
                )
        elif steps is not None:
            steps.append(
                {
                    "type": "proportional_zero",
                    "suffix": n.facility_suffix,
                    "remaining_need": _fq(n.shortage),
                }
            )
    return allocations


def fixed_priority_raw(
    asn_qty: Decimal,
    needs: List[FacilityNeed],
    *,
    steps: Optional[List[dict]] = None,
) -> Dict[str, Decimal]:
    eligible = sorted(_eligible(needs), key=lambda n: n.priority)
    remaining = asn_qty
    allocations: Dict[str, Decimal] = {}
    for n in eligible:
        if remaining <= 0:
            if steps is not None:
                steps.append(
                    {
                        "type": "asn_exhausted",
                        "suffix": n.facility_suffix,
                        "priority": n.priority,
                    }
                )
            continue
        qty = min(n.shortage, remaining)
        if qty > 0:
            allocations[n.facility_id] = qty
            remaining -= qty
            if steps is not None:
                steps.append(
                    {
                        "type": "priority_fill",
                        "suffix": n.facility_suffix,
                        "priority": n.priority,
                        "qty": _fq(qty),
                        "shortage": _fq(n.shortage),
                        "partial": qty < n.shortage,
                    }
                )
    return allocations


def largest_shortage_raw(
    asn_qty: Decimal,
    needs: List[FacilityNeed],
    *,
    steps: Optional[List[dict]] = None,
) -> Dict[str, Decimal]:
    eligible = sorted(_eligible(needs), key=lambda n: n.shortage, reverse=True)
    remaining = asn_qty
    allocations: Dict[str, Decimal] = {}
    rank = 0
    for n in eligible:
        rank += 1
        if remaining <= 0:
            if steps is not None:
                steps.append(
                    {
                        "type": "asn_exhausted",
                        "suffix": n.facility_suffix,
                        "rank": rank,
                        "shortage": _fq(n.shortage),
                    }
                )
            continue
        qty = min(n.shortage, remaining)
        if qty > 0:
            allocations[n.facility_id] = qty
            remaining -= qty
            if steps is not None:
                steps.append(
                    {
                        "type": "greedy_fill",
                        "suffix": n.facility_suffix,
                        "rank": rank,
                        "qty": _fq(qty),
                        "shortage": _fq(n.shortage),
                        "partial": qty < n.shortage,
                    }
                )
    return allocations


def _facility_scores(
    needs: List[FacilityNeed],
    shortage_weight: Decimal = DEFAULT_SHORTAGE_WEIGHT,
    priority_weight: Decimal = DEFAULT_PRIORITY_WEIGHT,
) -> List[Tuple[Decimal, FacilityNeed, dict]]:
    eligible = _eligible(needs)
    if not eligible:
        return []
    max_shortage = max(n.shortage for n in eligible)
    max_priority = max(n.priority for n in eligible)
    scored: List[Tuple[Decimal, FacilityNeed, dict]] = []
    for n in eligible:
        shortage_norm = n.shortage / max_shortage if max_shortage > 0 else Decimal("0")
        priority_norm = Decimal(max_priority - n.priority + 1) / Decimal(max_priority)
        score = shortage_weight * shortage_norm + priority_weight * priority_norm
        scored.append(
            (
                score,
                n,
                {
                    "shortage_norm": float(shortage_norm),
                    "priority_norm": float(priority_norm),
                    "score": float(score),
                },
            )
        )
    return scored


def weighted_score_raw(
    asn_qty: Decimal,
    needs: List[FacilityNeed],
    shortage_weight: Decimal = DEFAULT_SHORTAGE_WEIGHT,
    priority_weight: Decimal = DEFAULT_PRIORITY_WEIGHT,
    *,
    steps: Optional[List[dict]] = None,
) -> Dict[str, Decimal]:
    """Fill facilities in blended score order (default 70% shortage + 30% priority)."""
    scored = sorted(
        _facility_scores(needs, shortage_weight, priority_weight),
        key=lambda item: item[0],
        reverse=True,
    )
    if steps is not None:
        for rank, (score, n, meta) in enumerate(scored, start=1):
            steps.append(
                {
                    "type": "weighted_rank",
                    "suffix": n.facility_suffix,
                    "rank": rank,
                    "score": round(meta["score"], 3),
                    "shortage": _fq(n.shortage),
                    "priority": n.priority,
                }
            )
    remaining = asn_qty
    allocations: Dict[str, Decimal] = {}
    for score, n, _meta in scored:
        if remaining <= 0:
            if steps is not None:
                steps.append({"type": "asn_exhausted", "suffix": n.facility_suffix})
            continue
        qty = min(n.shortage, remaining)
        if qty > 0:
            allocations[n.facility_id] = qty
            remaining -= qty
            if steps is not None:
                steps.append(
                    {
                        "type": "weighted_fill",
                        "suffix": n.facility_suffix,
                        "qty": _fq(qty),
                        "shortage": _fq(n.shortage),
                        "partial": qty < n.shortage,
                    }
                )
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
    pallet_info: Optional[dict] = None,
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
                    "facility_suffix": n.facility_suffix,
                    "quantity": str(qty),
                    "handling_unit": "pallet",
                    "pallet_qty": str(pallet),
                    "recommendation": "crossdock",
                }
            )
            if pallet_info is not None:
                pallet_info.update(
                    {
                        "suffix": n.facility_suffix,
                        "qty": _fq(qty),
                        "pallet_qty": _fq(pallet),
                        "loose_remaining": _fq(remaining),
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

    pack_qty = needs[0].pack_qty if needs and needs[0].pack_qty > 0 else Decimal("0")
    pallet_qty = needs[0].pallet_qty if needs and needs[0].pallet_qty > 0 else Decimal("0")

    trace: dict = {
        "policy_key": policy_key,
        "asn_qty": _fq(asn_qty),
        "pack_qty": _fq(pack_qty) if pack_qty > 0 else None,
        "pallet_qty": _fq(pallet_qty) if pallet_qty > 0 else None,
        "facilities": facility_snapshots(needs),
        "policy_steps": [],
    }

    pallet_info: dict = {}
    pallet_alloc, loose_qty, crossdock = full_pallet_raw(asn_qty, needs, pallet_info)
    trace["pallet_crossdock"] = pallet_info if pallet_info else None
    trace["loose_qty"] = _fq(loose_qty)

    allocations: Dict[str, Decimal] = dict(pallet_alloc)
    notes: List[str] = []
    remainder_needs = needs

    if loose_qty > 0:
        remainder_needs = needs_with_remaining(needs, pallet_alloc) if pallet_alloc else needs
        trace["remainder_needs"] = remainder_snapshots(remainder_needs)
        extra = POLICY_RAW[policy_key](loose_qty, remainder_needs, steps=trace["policy_steps"])
        trace["remainder_raw"] = allocations_by_suffix(extra, needs)
        for fid, qty in extra.items():
            allocations[fid] = allocations.get(fid, Decimal("0")) + qty
    else:
        trace["remainder_needs"] = []
        trace["remainder_raw"] = {}

    trace["before_uom"] = allocations_by_suffix(allocations, needs)
    final, residual, uom_notes = apply_uom_and_limits(allocations, needs, asn_qty)
    notes.extend(uom_notes)
    trace["uom_notes"] = list(uom_notes)
    trace["final"] = allocations_by_suffix(final, needs)
    trace["residual"] = _fq(residual)

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
        trace=trace,
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
