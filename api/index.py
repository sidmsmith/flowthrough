# api/index.py
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flowthrough_service import create_orders, load_asn_data, plan_facility_orders  # noqa: E402
from mawm_client import get_manhattan_token  # noqa: E402

app = Flask(__name__)

PASSWORD = os.getenv("MANHATTAN_PASSWORD")
CLIENT_SECRET = os.getenv("MANHATTAN_SECRET")
USAGE_INGEST_URL = os.getenv("MANHATTAN_USAGE_INGEST_URL", "").strip()
APP_NAME = "flowthrough-app"
APP_VERSION = "1.0.0"

if not PASSWORD or not CLIENT_SECRET:
    raise Exception("Missing MANHATTAN_PASSWORD or MANHATTAN_SECRET environment variables")


def _json():
    return request.get_json(silent=True) or {}


def forward_usage_event(payload):
    if not USAGE_INGEST_URL:
        print("[usage] MANHATTAN_USAGE_INGEST_URL not set; event not recorded")
        return
    import requests

    try:
        requests.post(
            USAGE_INGEST_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=8,
            verify=False,
        )
    except Exception as e:
        print(f"[usage] Forward failed: {e}")


def _require_auth_fields(data):
    org = (data.get("org") or "").strip()
    token = (data.get("token") or "").strip()
    if not org or not token:
        return None, None, jsonify({"success": False, "error": "ORG and token required"})
    return org.upper(), token, None


@app.route("/api/app_opened", methods=["POST"])
def app_opened():
    return jsonify({"success": True})


@app.route("/api/auth", methods=["POST"])
def auth():
    org = (_json().get("org") or "").strip()
    if not org:
        return jsonify({"success": False, "error": "ORG required"})
    token = get_manhattan_token(org)
    if token:
        return jsonify({"success": True, "token": token})
    return jsonify({"success": False, "error": "Auth failed"})


@app.route("/api/load_asn", methods=["POST"])
def load_asn():
    data = _json()
    org, token, err = _require_auth_fields(data)
    if err:
        return err
    asn_id = (data.get("asn_id") or data.get("asnId") or "").strip().upper()
    if not asn_id:
        return jsonify({"success": False, "error": "ASN Id required"})
    location = (data.get("location") or "").strip() or None
    try:
        result = load_asn_data(org, token, asn_id, location)
        if result.get("success"):
            return jsonify(
                {
                    "success": True,
                    "asn": result["asn"],
                    "lines": result["lines"],
                    "receivingFacility": result["receivingFacility"],
                }
            )
        return jsonify(result)
    except PermissionError as e:
        return jsonify({"success": False, "error": str(e)}), 401
    except Exception as e:
        print(f"[LOAD_ASN] {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/preview_orders", methods=["POST"])
def preview_orders():
    data = _json()
    org, token, err = _require_auth_fields(data)
    if err:
        return err
    asn_id = (data.get("asn_id") or "").strip().upper()
    location = (data.get("location") or "").strip() or None
    selections = data.get("selections") or {}
    try:
        loaded = load_asn_data(org, token, asn_id, location)
        if not loaded.get("success"):
            return jsonify(loaded)
        plan = plan_facility_orders(
            org,
            token,
            asn_id,
            location or loaded["receivingFacility"],
            loaded["_parsed_lines"],
            loaded["_ui_lines_meta"],
            selections,
        )
        return jsonify(
            {
                "success": True,
                "orderCount": plan["orderCount"],
                "previewRows": plan["previewRows"],
            }
        )
    except Exception as e:
        print(f"[PREVIEW_ORDERS] {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/create_orders", methods=["POST"])
def create_orders_route():
    data = _json()
    org, token, err = _require_auth_fields(data)
    if err:
        return err
    asn_id = (data.get("asn_id") or "").strip().upper()
    location = (data.get("location") or "").strip() or None
    selections = data.get("selections") or {}
    try:
        loaded = load_asn_data(org, token, asn_id, location)
        if not loaded.get("success"):
            return jsonify(loaded)
        result = create_orders(
            org,
            token,
            asn_id,
            location or loaded["receivingFacility"],
            loaded["_parsed_lines"],
            loaded["_ui_lines_meta"],
            selections,
        )
        return jsonify(result)
    except PermissionError as e:
        return jsonify({"success": False, "error": str(e)}), 401
    except Exception as e:
        print(f"[CREATE_ORDERS] {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/usage-track", methods=["POST"])
def usage_track():
    data = _json()
    event_name = data.get("event_name")
    metadata = data.get("metadata", {})
    payload = {
        **metadata,
        "event_name": event_name,
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    forward_usage_event(payload)
    return jsonify({"success": True})
