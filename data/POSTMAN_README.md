# Flowthrough — Postman ASN Setup

Create demo ASNs individually via `/receiving/api/receiving/asn/save` (bulk import is **not** supported).

## Option A: Use `create_asns.py` (recommended)

```bash
cd flowthrough
pip install -r requirements.txt
python create_asns.py --all
```

## Option B: Postman manually

**Endpoint:** `POST https://salep.sce.manh.com/receiving/api/receiving/asn/save`

**Headers:**
- `Authorization: Bearer <token>`
- `Content-Type: application/json`
- `selectedOrganization: SS-DEMO`
- `selectedLocation: SS-DEMO-DM1`

Replace `SS-DEMO` with your ORG.

Payloads are in [`postman_asns.json`](postman_asns.json) — post each `save_payload` separately.

## Demo ASNs

| AsnId | Items | Qty | Highlights |
|-------|-------|-----|------------|
| ASNFLOW001 | 1000012 | 50 | Proportional vs fixed priority |
| ASNFLOW002 | 1000013 | 60 | All 4 policies differ (18/35/42 shortages) |
| ASNFLOW003 | 1000014 | 25 | Pack 5 — all 4 policies differ |
| ASNFLOW004 | 1000015 | 135 | Pallet 100 + remainder; default = fixed priority |
| ASNFLOW005 | 1125145 + 1000015 | 25 + 135 | Multi-line; line 1 mirrors 003 on item 1125145 |

## Verify / filter in MAWM

List all flowthrough ASNs:

```json
{ "Query": "AsnId like 'ASNFLOW%'" }
```

Single ASN:

```json
{ "Query": "AsnId = 'ASNFLOW001'" }
```
