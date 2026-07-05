#!/usr/bin/env python3
"""Shared MAWM API client for flowthrough scripts."""

import os
import re
import calendar
import urllib3
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HOST = "https://salep.sce.manh.com"
AUTH_HOST = os.getenv("MANHATTAN_AUTH_HOST", "salep-auth.sce.manh.com")
ASN_SEARCH_URL = f"{HOST}/receiving/api/receiving/asn/search"
ASN_SAVE_URL = f"{HOST}/receiving/api/receiving/asn/save"
ITEM_SEARCH_URL = f"{HOST}/item-master/api/item-master/item/search"
ORDER_SAVE_URL = f"{HOST}/dcorder/api/dcorder/order"
ORDER_SEARCH_URL = f"{HOST}/dcorder/api/dcorder/order/search"
ORDER_TYPE = "Fast Flow"
ORDER_STATUS = "1000"


def add_months(dt: datetime, months: int) -> datetime:
    """Add calendar months, clamping day when needed (e.g. Jan 31 + 1 month → Feb 28/29)."""
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def build_order_schedule(now: datetime = None) -> dict:
    """
    Pickup window starts now; pickup end +1 month.
    Delivery start/end are each +1 day after the corresponding pickup time.
    """
    pickup_start = now or datetime.now().replace(microsecond=0)
    pickup_end = add_months(pickup_start, 1)
    delivery_start = pickup_start + timedelta(days=1)
    delivery_end = pickup_end + timedelta(days=1)

    def fmt(dt: datetime) -> str:
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    return {
        "PickupStartDateTime": fmt(pickup_start),
        "PickupEndDateTime": fmt(pickup_end),
        "DeliveryStartDateTime": fmt(delivery_start),
        "DeliveryEndDateTime": fmt(delivery_end),
    }
USERNAME_BASE = os.getenv("MANHATTAN_USERNAME_BASE", "sdtadmin@")
CLIENT_ID = os.getenv("MANHATTAN_CLIENT_ID", "omnicomponent.1.0.0")
REQUEST_TIMEOUT = 60

# Avoid corporate/system proxies stripping Authorization (Postman often bypasses proxy).
_session = requests.Session()
_session.trust_env = False
_NO_PROXY = {"http": None, "https": None}


def _post(url: str, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    kwargs.setdefault("verify", False)
    kwargs.setdefault("proxies", _NO_PROXY)
    return _session.post(url, **kwargs)


def normalize_token(token: str) -> str:
    """Clean pasted tokens: strip whitespace, quotes, and redundant Bearer prefix."""
    token = (token or "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ('"', "'"):
        token = token[1:-1].strip()
    return token


def resolve_location(org: str, location: str = None, default_suffix: str = "DM1") -> str:
    """Resolve full facility id for selectedLocation / FacilityId headers."""
    org = org.upper()
    if location and str(location).strip():
        loc = str(location).strip().upper()
        if loc.startswith(org):
            return loc
        if "-" in loc:
            return loc
        return f"{org}-{loc}"
    return f"{org}-{default_suffix}"


def build_receiving_headers(token: str, org: str, facility_suffix: str = "DM1", location: str = None) -> dict:
    """Headers for receiving ASN save/search — matches Postman (no FacilityId)."""
    org = org.upper()
    loc = resolve_location(org, location, facility_suffix)
    token = normalize_token(token)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "selectedOrganization": org,
        "selectedLocation": loc,
    }


def build_headers(token: str, org: str, facility_suffix: str = "DM1") -> dict:
    """Alias for receiving APIs."""
    return build_receiving_headers(token, org, facility_suffix)


def get_manhattan_token(org: str) -> Optional[str]:
    """Obtain OAuth token using MANHATTAN_PASSWORD and MANHATTAN_SECRET env vars."""
    password = os.getenv("MANHATTAN_PASSWORD", "").strip()
    secret = os.getenv("MANHATTAN_SECRET", "").strip()
    if not password or not secret:
        return None

    url = f"https://{AUTH_HOST}/oauth/token"
    username = f"{USERNAME_BASE}{org.lower()}"
    data = {
        "grant_type": "password",
        "username": username,
        "password": password,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    auth = HTTPBasicAuth(CLIENT_ID, secret)
    try:
        response = _post(url, data=data, headers=headers, auth=auth)
        if response.status_code == 200:
            return response.json().get("access_token")
        print(f"OAuth failed ({response.status_code}): {response.text[:300]}")
    except requests.RequestException as exc:
        print(f"OAuth error: {exc}")
    return None


def verify_auth(token: str, org: str) -> Tuple[bool, str]:
    """
    Optional sanity check — confirms ASN search works with this token.
    Uses the same headers as create_asns / Postman.
    """
    token = normalize_token(token)
    payload = {"Query": "AsnId ='ASNFLOW001'"}
    response = _post(
        ASN_SEARCH_URL,
        headers=build_receiving_headers(token, org),
        json=payload,
    )
    if response.status_code in (401, 403):
        return False, (
            f"ASN search rejected ({response.status_code}). "
            f"Token length={len(token)}. Response: {response.text[:300]}"
        )
    if response.status_code != 200:
        return False, f"ASN search check failed ({response.status_code}): {response.text[:300]}"
    return True, "Token verified via ASN search."


def build_order_headers(token: str, org: str, facility_id: str) -> dict:
    org = org.upper()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "FacilityId": facility_id,
        "selectedOrganization": org,
        "selectedLocation": facility_id,
    }


def search_asn(asn_id: str, token: str, org: str, location: str = None) -> Optional[dict]:
    token = normalize_token(token)
    payload = {"Query": f"AsnId ='{asn_id}'"}
    headers = build_receiving_headers(token, org, location=location)
    response = _post(ASN_SEARCH_URL, headers=headers, json=payload)
    if response.status_code in (401, 403):
        raise PermissionError(
            f"ASN search rejected ({response.status_code}). "
            f"Response: {response.text[:500]}"
        )
    if response.status_code != 200:
        raise RuntimeError(f"ASN search failed: {response.status_code} {response.text[:500]}")
    body = response.json()
    data = body.get("data") or body.get("Data") or []
    if not data:
        payload_with_page = {**payload, "Page": 0, "Size": 20}
        response = _post(ASN_SEARCH_URL, headers=headers, json=payload_with_page)
        if response.status_code != 200:
            raise RuntimeError(f"ASN search failed: {response.status_code} {response.text[:500]}")
        body = response.json()
        data = body.get("data") or body.get("Data") or []
    return data[0] if data else None


def _response_data_list(body: dict) -> List[dict]:
    data = body.get("data") or body.get("Data") or []
    return data if isinstance(data, list) else []


def search_orders(query: str, token: str, org: str, location: str = None, size: int = 1) -> List[dict]:
    """Search dc orders; returns matching order header rows."""
    token = normalize_token(token)
    origin = resolve_location(org, location)
    payload = {
        "Query": query,
        "Page": 0,
        "Size": size,
        "Template": {"OrderId": ""},
    }
    response = _post(
        ORDER_SEARCH_URL,
        headers=build_order_headers(token, org, origin),
        json=payload,
    )
    if response.status_code in (401, 403):
        raise PermissionError(
            f"Order search rejected ({response.status_code}). "
            f"Response: {response.text[:500]}"
        )
    if response.status_code != 200:
        raise RuntimeError(f"Order search failed: {response.status_code} {response.text[:500]}")
    return _response_data_list(response.json())


def flow_orders_exist(asn_id: str, token: str, org: str, location: str = None) -> bool:
    """True when any replenishment order exists for FLOW-{asn_id}*."""
    asn_id = (asn_id or "").strip().upper()
    query = f"(OrderId _ FLOW-{asn_id}%)"
    return len(search_orders(query, token, org, location=location, size=1)) > 0


def save_asn(payload: dict, token: str, org: str) -> requests.Response:
    token = normalize_token(token)
    return _post(
        ASN_SAVE_URL,
        headers=build_receiving_headers(token, org),
        json=payload,
    )


def search_items(item_ids: List[str], token: str, org: str, location: str = None) -> Dict[str, dict]:
    clean = [str(i).strip() for i in item_ids if str(i).strip()]
    if not clean:
        return {}
    quoted = ", ".join(f"'{item_id}'" for item_id in clean)
    payload = {
        "Query": f"ItemId in ({quoted})",
        "Page": 0,
        "Size": max(len(clean), 50),
        "Template": {
            "ItemId": "",
            "StandardPackQuantity": "",
            "StandardLpnQuantity": "",
            "ItemPackage": [
                {
                    "Standard": "",
                    "StandardQuantityUomId": "",
                    "Quantity": "",
                    "UomId": "",
                }
            ],
        },
    }
    headers = build_receiving_headers(token, org, location=location)
    headers["FacilityId"] = resolve_location(org, location)
    try:
        response = _post(ITEM_SEARCH_URL, headers=headers, json=payload)
    except requests.RequestException as exc:
        print(f"Warning: item search failed: {exc}")
        return {}
    if response.status_code != 200:
        print(f"Warning: item search failed: {response.status_code}")
        return {}
    body = response.json()
    data = body.get("data") or body.get("Data") or [] if isinstance(body, dict) else []
    return {str(item.get("ItemId")): item for item in data if item.get("ItemId")}


def item_uom_quantities(item: dict):
    pack = _dec(item.get("StandardPackQuantity"))
    pallet = _dec(item.get("StandardLpnQuantity"))
    return pack, pallet


def _dec(value) -> Optional[Decimal]:
    if value in (None, "", []):
        return None
    try:
        d = Decimal(str(value))
        return d if d > 0 else None
    except Exception:
        return None


def save_facility_order(
    token: str,
    org: str,
    asn_id: str,
    destination_facility_id: str,
    order_lines: List[dict],
    origin_facility_id: str = None,
    order_type: str = ORDER_TYPE,
    location: str = None,
) -> dict:
    """
    Save one replenishment order for a destination facility.

    order_lines: list of dicts with order_line_id, item_id, quantity, uom.
    OrderId format: FLOW-{AsnId}-{FacilitySuffix} (e.g. FLOW-ASNFLOW005-DM2).
    """
    origin = origin_facility_id or resolve_location(org, location)
    org = org.upper()
    order_id = f"FLOW-{asn_id}-{destination_facility_id.split('-')[-1]}"
    payload_lines = []
    for line in order_lines:
        qty = line["quantity"]
        qty_val = Decimal(str(qty))
        ordered_qty = (
            int(qty_val)
            if qty_val == qty_val.to_integral_value()
            else float(qty_val)
        )
        payload_lines.append(
            {
                "OrderLineId": str(line["order_line_id"]),
                "OrderId": order_id,
                "OrgId": org,
                "FacilityId": origin,
                "ItemId": line["item_id"],
                "OrderedQuantity": ordered_qty,
                "QuantityUomId": line.get("uom") or "UNIT",
                "Order": {"OrderId": order_id},
            }
        )
    payload = {
        "OrderId": order_id,
        "OrgId": org,
        "FacilityId": origin,
        "OriginFacilityId": origin,
        "DestinationFacilityId": destination_facility_id,
        "OrderType": order_type,
        "MaximumStatus": ORDER_STATUS,
        "MinimumStatus": ORDER_STATUS,
        **build_order_schedule(),
        "OrderLine": payload_lines,
    }
    response = _post(
        ORDER_SAVE_URL,
        headers=build_order_headers(token, org, origin),
        json=payload,
    )
    return {
        "order_id": order_id,
        "destination_facility_id": destination_facility_id,
        "order_lines": payload_lines,
        "status_code": response.status_code,
        "success": response.status_code in (200, 201),
        "response": response.text[:1000],
    }


def save_replenishment_order(
    token: str,
    org: str,
    destination_facility_id: str,
    item_id: str,
    quantity,
    uom: str,
    asn_id: str,
    order_seq: int = 1,
) -> dict:
    """Legacy single-line helper — prefer save_facility_order for multi-line orders."""
    return save_facility_order(
        token,
        org,
        asn_id,
        destination_facility_id,
        [
            {
                "order_line_id": "1",
                "item_id": item_id,
                "quantity": quantity,
                "uom": uom,
            }
        ],
    )


def validate_org(org: str) -> bool:
    return bool(re.match(r"^[A-Z0-9]+-DEMO$", org or ""))
