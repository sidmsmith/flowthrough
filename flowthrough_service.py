"""Flowthrough web API — ASN load, allocation preview, order creation."""

from decimal import Decimal
from typing import Dict, List, Optional

from allocation.algorithms import POLICY_KEYS
from allocation.engine import _part_kwargs, resolve_default_algorithm, run_all_algorithms
from allocation.models import PartParams
from allocation.need import is_allocatable
from config_loader import load_config, receiving_facility_id
from mawm_client import (
    flow_orders_exist,
    item_uom_quantities,
    resolve_location,
    save_facility_order,
    search_asn,
    search_items,
)
from order_builder import (
    accumulate_line_allocations,
    build_order_id,
    new_facility_order_buckets,
    renumber_order_lines,
)


def _dec(value) -> Optional[Decimal]:
    if value in (None, "", []):
        return None
    try:
        d = Decimal(str(value))
        return d if d > 0 else None
    except Exception:
        return None


def parse_asn_lines(asn: dict) -> List[dict]:
    lines = asn.get("AsnLine") or []
    parsed = []
    for line in lines:
        item_id = str(line.get("ItemId") or "").strip()
        if not item_id:
            continue
        parsed.append(
            {
                "item_id": item_id,
                "quantity": Decimal(str(line.get("ShippedQuantity") or 0)),
                "uom": line.get("QuantityUomId") or "UNIT",
                "asn_line_id": line.get("AsnLineId"),
            }
        )
    return parsed


def format_qty(qty) -> str:
    d = Decimal(str(qty))
    if d == d.to_integral_value():
        return str(int(d))
    return str(d.normalize())


def format_alloc_cell(qty, pack_qty=None) -> str:
    if qty in (None, "", 0, Decimal("0")):
        return "0" if not pack_qty or pack_qty <= 0 else "0 / 0pk"
    if not pack_qty or pack_qty <= 0:
        return format_qty(qty)
    qty = Decimal(str(qty))
    pack_qty = Decimal(str(pack_qty))
    packs = qty / pack_qty
    if packs == packs.to_integral_value():
        return f"{format_qty(qty)} / {int(packs)}pk"
    return format_qty(qty)


def _part_for_item(config: dict, item_id: str) -> Optional[PartParams]:
    part_row = next((p for p in config.get("parts", []) if p["item_id"] == item_id), None)
    if not part_row:
        return None
    return PartParams(**_part_kwargs(part_row))


def _need_row(n) -> dict:
    return {
        "facility": n.facility_suffix,
        "position": int(n.inventory_position) if n.inventory_position == n.inventory_position.to_integral_value() else float(n.inventory_position),
        "shortage": int(n.shortage) if n.shortage == n.shortage.to_integral_value() else float(n.shortage),
        "max": int(n.max_qty) if n.max_qty == n.max_qty.to_integral_value() else float(n.max_qty),
        "available": int(n.available_qty) if n.available_qty == n.available_qty.to_integral_value() else float(n.available_qty),
        "inbound": int(n.inbound_qty) if n.inbound_qty == n.inbound_qty.to_integral_value() else float(n.inbound_qty),
        "outbound": int(n.outbound_qty) if n.outbound_qty == n.outbound_qty.to_integral_value() else float(n.outbound_qty),
        "excluded": not is_allocatable(n),
    }


def _line_ui_payload(
    line_num: int,
    item_id: str,
    asn_qty: Decimal,
    uom: str,
    org: str,
    config: dict,
    item_lookup: dict,
) -> dict:
    item = item_lookup.get(item_id, {})
    pack, pallet = item_uom_quantities(item)
    part = _part_for_item(config, item_id)
    default_key = resolve_default_algorithm(part, config)
    needs, results, default_key = run_all_algorithms(asn_qty, org, item_id, config, pack, pallet)

    pack_qty = None
    if needs and needs[0].pack_qty and needs[0].pack_qty > 0:
        pack_qty = needs[0].pack_qty
    elif pack and pack > 0:
        pack_qty = pack

    facility_order = [n.facility_suffix for n in needs]
    policies = {}
    units = {}
    residual = {}

    for key in POLICY_KEYS:
        result = results[key]
        policies[key] = {}
        units[key] = {}
        for n in needs:
            fid = n.facility_id
            suffix = n.facility_suffix
            qty = result.allocations.get(fid, Decimal("0"))
            policies[key][suffix] = format_alloc_cell(qty, pack_qty)
            units[key][suffix] = int(qty) if qty == qty.to_integral_value() else float(qty)
        residual[key] = int(result.residual_qty) if result.residual_qty == result.residual_qty.to_integral_value() else float(result.residual_qty)

    pack_display = int(pack_qty) if pack_qty and pack_qty == pack_qty.to_integral_value() else (float(pack_qty) if pack_qty else None)
    pallet_display = None
    if needs and needs[0].pallet_qty and needs[0].pallet_qty > 0:
        p = needs[0].pallet_qty
        pallet_display = int(p) if p == p.to_integral_value() else float(p)

    return {
        "lineNum": line_num,
        "itemId": item_id,
        "qty": int(asn_qty) if asn_qty == asn_qty.to_integral_value() else float(asn_qty),
        "uom": uom,
        "packQty": pack_display,
        "palletQty": pallet_display,
        "defaultAlgo": default_key,
        "needs": [_need_row(n) for n in needs],
        "policies": policies,
        "units": units,
        "residual": residual,
        "_facility_order": facility_order,
    }


def asn_header_payload(asn: dict, line_count: int) -> dict:
    return {
        "asnId": asn.get("AsnId") or "",
        "estimatedReceiptDate": asn.get("EstimatedReceiptDate") or asn.get("estimatedReceiptDate"),
        "asnStatus": asn.get("AsnStatus") if asn.get("AsnStatus") is not None else asn.get("asnStatus"),
        "vendorId": asn.get("VendorId") or asn.get("vendorId") or "",
        "lineCount": line_count,
    }


REQUIRED_ASN_STATUS = 1000

_ASN_STATUS_LABELS = {
    0: "Un-Shipped",
    1000: "In Transit",
    2000: "Unloaded",
    3000: "In Receiving",
    8000: "Verified",
    9000: "Cancelled",
}


def _asn_status_code(asn: dict):
    raw = asn.get("AsnStatus") if asn.get("AsnStatus") is not None else asn.get("asnStatus")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def load_asn_data(org: str, token: str, asn_id: str, location: str = None) -> dict:
    config = load_config()
    asn_id = (asn_id or "").strip().upper()
    asn = search_asn(asn_id, token, org, location=location)
    if not asn:
        return {"success": False, "error": f"ASN not found: {asn_id}"}

    status_code = _asn_status_code(asn)
    if status_code != REQUIRED_ASN_STATUS:
        label = _ASN_STATUS_LABELS.get(status_code, str(status_code if status_code is not None else "—"))
        return {
            "success": False,
            "error": f"ASN {asn_id} must be In Transit (status 1000). Current status: {label}.",
        }

    try:
        if flow_orders_exist(asn_id, token, org, location=location):
            return {
                "success": False,
                "error": f"Outbound orders already exist for {asn_id}",
            }
    except PermissionError:
        raise
    except Exception as e:
        return {
            "success": False,
            "error": f"Unable to verify existing orders for {asn_id}: {e}",
        }

    lines = parse_asn_lines(asn)
    if not lines:
        return {"success": False, "error": "ASN has no lines with ItemId / ShippedQuantity."}

    item_lookup = search_items([ln["item_id"] for ln in lines], token, org, location=location)
    ui_lines = []
    for i, line in enumerate(lines, start=1):
        ui_lines.append(
            _line_ui_payload(
                i,
                line["item_id"],
                line["quantity"],
                line["uom"],
                org,
                config,
                item_lookup,
            )
        )

    receiving = location or receiving_facility_id(org, config)
    return {
        "success": True,
        "asn": asn_header_payload(asn, len(ui_lines)),
        "lines": [{k: v for k, v in ln.items() if not k.startswith("_")} for ln in ui_lines],
        "receivingFacility": receiving,
        "_parsed_lines": lines,
        "_ui_lines_meta": ui_lines,
    }


def _selections_for_lines(ui_lines_meta: List[dict], selections: dict) -> Dict[int, str]:
    chosen = {}
    for ln in ui_lines_meta:
        key = str(ln["lineNum"])
        algo = selections.get(key) or selections.get(ln["lineNum"]) or ln["defaultAlgo"]
        if algo not in POLICY_KEYS:
            algo = ln["defaultAlgo"]
        chosen[ln["lineNum"]] = algo
    return chosen


def plan_facility_orders(
    org: str,
    token: str,
    asn_id: str,
    location: str,
    parsed_lines: List[dict],
    ui_lines_meta: List[dict],
    selections: dict,
) -> dict:
    config = load_config()
    receiving = location or receiving_facility_id(org, config)
    chosen = _selections_for_lines(ui_lines_meta, selections)
    buckets = new_facility_order_buckets()

    for ln_meta, parsed in zip(ui_lines_meta, parsed_lines):
        algo = chosen[ln_meta["lineNum"]]
        units = ln_meta["units"].get(algo, {})
        allocations = {}
        for suffix, qty in units.items():
            if Decimal(str(qty)) <= 0:
                continue
            full_id = f"{org.upper()}-{suffix}" if not str(suffix).upper().startswith(org.upper()) else str(suffix).upper()
            allocations[full_id] = Decimal(str(qty))
        accumulate_line_allocations(
            buckets,
            parsed["item_id"],
            parsed["uom"],
            allocations,
        )

    facility_orders = renumber_order_lines(buckets)
    order_count = len(facility_orders)
    preview_rows = []
    for dest, order_lines in facility_orders.items():
        order_id = build_order_id(asn_id, dest)
        for ol in order_lines:
            preview_rows.append(
                {
                    "orderId": order_id,
                    "destination": dest,
                    "orderLineId": ol["order_line_id"],
                    "itemId": ol["item_id"],
                    "qty": format_qty(ol["quantity"]),
                    "uom": ol["uom"],
                }
            )

    return {
        "orderCount": order_count,
        "facilityOrders": facility_orders,
        "previewRows": preview_rows,
        "receivingFacility": receiving,
    }


def create_orders(
    org: str,
    token: str,
    asn_id: str,
    location: str,
    parsed_lines: List[dict],
    ui_lines_meta: List[dict],
    selections: dict,
) -> dict:
    plan = plan_facility_orders(org, token, asn_id, location, parsed_lines, ui_lines_meta, selections)
    facility_orders = plan["facilityOrders"]
    if not facility_orders:
        return {
            "success": True,
            "orderCount": 0,
            "orders": [],
            "message": "No allocations to order for this ASN.",
        }

    origin = plan["receivingFacility"]
    results = []
    sorted_dests = sorted(facility_orders.keys(), key=lambda dest: build_order_id(asn_id, dest))
    for dest in sorted_dests:
        lines = facility_orders[dest]
        order_result = save_facility_order(
            token,
            org,
            asn_id,
            dest,
            lines,
            origin_facility_id=origin,
            location=origin,
        )
        order_id = order_result["order_id"]
        for ol in lines:
            results.append(
                {
                    "orderId": order_id,
                    "destination": dest,
                    "orderLineId": ol["order_line_id"],
                    "itemId": ol["item_id"],
                    "qty": format_qty(ol["quantity"]),
                    "uom": ol["uom"],
                    "success": order_result["success"],
                    "status": "OK" if order_result["success"] else "FAILED",
                    "response": order_result.get("response", "")[:200],
                }
            )

    ok_orders = len({r["orderId"] for r in results if r["success"]})
    failed_orders = len({r["orderId"] for r in results if not r["success"]})
    order_word = "order" if ok_orders == 1 else "orders"
    fail_word = "order" if failed_orders == 1 else "orders"
    if ok_orders == 0 and failed_orders:
        message = f"No replenishment orders were created for ASN {asn_id}. {failed_orders} {fail_word} failed."
    elif failed_orders:
        message = (
            f"Created {ok_orders} replenishment {order_word} for ASN {asn_id}. "
            f"{failed_orders} {fail_word} failed."
        )
    else:
        message = f"Created {ok_orders} replenishment {order_word} for ASN {asn_id}."
    return {
        "success": all(r["success"] for r in results) if results else True,
        "orderCount": ok_orders,
        "orders": results,
        "message": message,
    }
