"""Build human-readable allocation explanations from policy traces."""

from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from allocation.algorithms import POLICY_KEYS
from allocation.models import AllocationResult, FacilityNeed


def _num_list(parts: List[str]) -> str:
    return ", ".join(parts)


def _eligible_shortage_total(trace: dict) -> int:
    total = Decimal("0")
    for row in trace.get("facilities") or []:
        if row.get("allocatable"):
            total += Decimal(str(row.get("shortage") or 0))
    return int(total) if total == total.to_integral_value() else float(total)


def _pack_note(trace: dict) -> Optional[str]:
    pack = trace.get("pack_qty")
    if pack:
        return f"Pack size {pack} enforced — allocations rounded to full packs."
    return None


def _pallet_note(trace: dict) -> List[str]:
    pallet = trace.get("pallet_qty")
    cross = trace.get("pallet_crossdock")
    if not cross:
        return []
    lines = [
        f"Pallet pass: {_fq(cross.get('qty'))} units crossdocked to {cross.get('suffix')} "
        f"(pallet size {cross.get('pallet_qty')}).",
        f"Loose remainder after crossdock: {cross.get('loose_remaining')} units.",
    ]
    if pallet:
        lines[0] = lines[0]  # already includes pallet size
    return lines


def _fq(val) -> str:
    if val in (None, ""):
        return "0"
    d = Decimal(str(val))
    if d == d.to_integral_value():
        return str(int(d))
    return str(d.normalize())


def _uom_detail_lines(trace: dict) -> List[str]:
  notes = trace.get("uom_notes") or []
  return [n for n in notes if n]


def _final_qty(trace: dict, suffix: str) -> str:
    return (trace.get("final") or {}).get(suffix) or "0"


def _explain_proportional_column(trace: dict) -> Tuple[str, List[str]]:
    asn = trace.get("asn_qty")
    total = _eligible_shortage_total(trace)
    details = []
    if trace.get("pallet_crossdock"):
        details.extend(_pallet_note(trace))
        details.append("Remainder split proportionally on remaining need after crossdock.")
    else:
        details.append(f"Eligible shortages total {total}; ASN is {asn}.")
    pack = _pack_note(trace)
    if pack:
        details.append(pack)
    details.extend(_uom_detail_lines(trace))

    parts = []
    for step in trace.get("policy_steps") or []:
        if step.get("type") == "proportional_share":
            pct = step.get("share_pct")
            if pct is not None:
                parts.append(f"{step['suffix']} {_fq(step.get('qty'))} ({pct}% share)")
            else:
                parts.append(f"{step['suffix']} {_fq(step.get('qty'))} (rounding remainder)")

    summary = (
        f"{asn} units split by each store's share of total shortage ({total}). "
        f"Result: {_num_list(parts) or 'no eligible stores'}."
    )
    if int(_fq(trace.get("residual") or 0)) > 0:
        summary += f" {trace.get('residual')} units residual after pack rules."
    return summary, details


def _explain_fixed_column(trace: dict) -> Tuple[str, List[str]]:
    asn = trace.get("asn_qty")
    details = []
    if trace.get("pallet_crossdock"):
        details.extend(_pallet_note(trace))
    details.append("Fill stores in priority order (DM2 → DM3 → …) until ASN runs out.")
    pack = _pack_note(trace)
    if pack:
        details.append(pack)
    details.extend(_uom_detail_lines(trace))

    filled = []
    starved = []
    for step in trace.get("policy_steps") or []:
        if step.get("type") == "priority_fill":
            if step.get("partial"):
                filled.append(
                    f"{step['suffix']} {_fq(step.get('qty'))} of {_fq(step.get('shortage'))} shortage"
                )
            else:
                filled.append(f"{step['suffix']} {_fq(step.get('qty'))} (full shortage)")
        elif step.get("type") == "asn_exhausted":
            starved.append(step["suffix"])

    summary = f"{asn} units assigned by facility priority."
    if filled:
        summary += f" Filled: {_num_list(filled)}."
    if starved:
        summary += f" No stock for: {_num_list(starved)} — ASN exhausted."
    return summary, details


def _explain_largest_column(trace: dict) -> Tuple[str, List[str]]:
    asn = trace.get("asn_qty")
    details = []
    if trace.get("pallet_crossdock"):
        details.extend(_pallet_note(trace))
    details.append("Greedy fill: largest remaining shortage first.")
    pack = _pack_note(trace)
    if pack:
        details.append(pack)
    details.extend(_uom_detail_lines(trace))

    filled = []
    starved = []
    for step in trace.get("policy_steps") or []:
        if step.get("type") == "greedy_fill":
            filled.append(f"{step['suffix']} {_fq(step.get('qty'))}")
        elif step.get("type") == "asn_exhausted":
            starved.append(step["suffix"])

    summary = f"{asn} units assigned to the largest gaps first."
    if filled:
        summary += f" Received: {_num_list(filled)}."
    if starved:
        summary += f" Starved: {_num_list(starved)}."
    return summary, details


def _explain_weighted_column(trace: dict) -> Tuple[str, List[str]]:
    asn = trace.get("asn_qty")
    details = []
    if trace.get("pallet_crossdock"):
        details.extend(_pallet_note(trace))
    details.append("Rank by 70% shortage + 30% priority, then fill in score order.")
    pack = _pack_note(trace)
    if pack:
        details.append(pack)

    ranks = []
    for step in trace.get("policy_steps") or []:
        if step.get("type") == "weighted_rank":
            ranks.append(
                f"{step['rank']}. {step['suffix']} score {step.get('score')} "
                f"(shortage {step.get('shortage')}, priority {step.get('priority')})"
            )
    if ranks:
        details.append("Ranking: " + "; ".join(ranks))
    details.extend(_uom_detail_lines(trace))

    filled = []
    starved = []
    for step in trace.get("policy_steps") or []:
        if step.get("type") == "weighted_fill":
            filled.append(f"{step['suffix']} {_fq(step.get('qty'))}")
        elif step.get("type") == "asn_exhausted":
            starved.append(step["suffix"])

    summary = f"{asn} units assigned by weighted score ranking."
    if filled:
        summary += f" Received: {_num_list(filled)}."
    if starved:
        summary += f" Starved: {_num_list(starved)}."
    return summary, details


COLUMN_EXPLAINERS = {
    "proportional": _explain_proportional_column,
    "fixed_priority": _explain_fixed_column,
    "largest_shortage": _explain_largest_column,
    "weighted_score": _explain_weighted_column,
}


def _facility_proportional(trace: dict, suffix: str) -> Tuple[str, List[str]]:
    qty = _final_qty(trace, suffix)
    for step in trace.get("policy_steps") or []:
        if step.get("suffix") != suffix:
            continue
        if step.get("type") == "proportional_share":
            pct = step.get("share_pct")
            if pct is not None:
                return (
                    f"{qty} units — {pct}% of the ASN based on shortage share.",
                    [f"Remaining need: {step.get('remaining_need')}."],
                )
            return (
                f"{qty} units — receives rounding remainder from proportional pass.",
                [],
            )
        if step.get("type") == "proportional_zero":
            return ("0 units — fair-share pass rounded to zero for this store.", [])
    if trace.get("pallet_crossdock") and trace["pallet_crossdock"].get("suffix") == suffix:
        p = trace["pallet_crossdock"]
        loose = (trace.get("remainder_raw") or {}).get(suffix)
        parts = [f"Pallet crossdock: {p.get('qty')} units."]
        if loose:
            parts.append(f"Plus {loose} loose from remainder pass → total {qty}.")
        return (f"{qty} units total including pallet crossdock.", parts)
    if qty != "0":
        return (f"{qty} units after pack rounding.", _uom_detail_lines(trace))
    return ("0 units — not allocated under this policy.", [])


def _facility_priority(trace: dict, suffix: str) -> Tuple[str, List[str]]:
    qty = _final_qty(trace, suffix)
    if trace.get("pallet_crossdock") and trace["pallet_crossdock"].get("suffix") == suffix:
        base = f"{qty} units including pallet crossdock"
    else:
        base = f"{qty} units"
    for step in trace.get("policy_steps") or []:
        if step.get("suffix") != suffix:
            continue
        if step.get("type") == "priority_fill":
            if step.get("partial"):
                return (
                    f"{base} — partial fill; {step.get('qty')} of {step.get('shortage')} shortage (priority {step.get('priority')}).",
                    [],
                )
            return (
                f"{base} — full shortage filled (priority {step.get('priority')}).",
                [],
            )
        if step.get("type") == "asn_exhausted":
            return (
                f"0 units — ASN exhausted before this store (priority {step.get('priority')}).",
                [],
            )
    if qty != "0":
        return (f"{base} from priority-ordered remainder.", [])
    return ("0 units — not reached in priority order.", [])


def _facility_greedy(trace: dict, suffix: str, label: str) -> Tuple[str, List[str]]:
    qty = _final_qty(trace, suffix)
    if trace.get("pallet_crossdock") and trace["pallet_crossdock"].get("suffix") == suffix:
        p = trace["pallet_crossdock"]
        return (
            f"{qty} units — includes {p.get('qty')} pallet crossdock.",
            [],
        )
    for step in trace.get("policy_steps") or []:
        if step.get("suffix") != suffix:
            continue
        if step.get("type") in ("greedy_fill", "weighted_fill"):
            rank = step.get("rank")
            rank_txt = f"rank {rank}" if rank else label
            if step.get("partial"):
                return (
                    f"{qty} units — {rank_txt}; partial fill of {step.get('shortage')} shortage.",
                    [],
                )
            return (f"{qty} units — {rank_txt}; full shortage filled.", [])
        if step.get("type") == "asn_exhausted":
            return (f"0 units — ASN exhausted before this store ({label}).", [])
    if qty != "0":
        return (f"{qty} units after allocation and pack rules.", [])
    return ("0 units — not allocated.", [])


FACILITY_EXPLAINERS = {
    "proportional": _facility_proportional,
    "fixed_priority": _facility_priority,
    "largest_shortage": lambda t, s: _facility_greedy(t, s, "largest shortage"),
    "weighted_score": lambda t, s: _facility_greedy(t, s, "weighted score"),
}


def explain_policy(trace: Optional[dict], needs: List[FacilityNeed]) -> dict:
    if not trace:
        return {}
    key = trace.get("policy_key")
    explain_col = COLUMN_EXPLAINERS.get(key)
    if not explain_col:
        return {}
    summary, details = explain_col(trace)
    suffixes = [n.facility_suffix for n in needs if n.max_qty > 0]
    facilities = {}
    fac_fn = FACILITY_EXPLAINERS.get(key)
    if fac_fn:
        for suffix in suffixes:
            f_summary, f_details = fac_fn(trace, suffix)
            facilities[suffix] = {"summary": f_summary, "details": f_details}
    return {"summary": summary, "details": details, "facilities": facilities}


def build_line_explanations(
    needs: List[FacilityNeed],
    results: Dict[str, AllocationResult],
) -> dict:
    out = {}
    for key in POLICY_KEYS:
        result = results.get(key)
        if not result:
            continue
        block = explain_policy(result.trace, needs)
        if block:
            out[key] = block
    return out
