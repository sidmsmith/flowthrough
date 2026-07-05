# Flowthrough — ASN-Driven Replenishment Demo

CLI tools and a **web app** for demonstrating ASN-driven replenishment and crossdock allocation against the MAWM demo environment (`salep.sce.manh.com`).

- **Web app:** [flowthrough.vercel.app](https://flowthrough.vercel.app) — see [DEPLOY.md](DEPLOY.md)
- **CLI:** preview allocation columns and create orders from the terminal

Simulated multi-facility inventory lives in a local JSON file (`data/facility_inventory.json`). Destination facilities use org-relative IDs (`DM2`–`DM5` → `{ORG}-DM2`, etc.).

## Setup

```bash
cd flowthrough
pip install -r requirements.txt
```

## Demo ASNs

Demo ASN ids: **FLOW001** through **FLOW006** (filter in MAWM: `AsnId like 'FLOW%'`).

| AsnId | Focus |
|-------|-------|
| FLOW001 | Proportional vs fixed priority |
| FLOW002 | Qty 60 — all four policies differ |
| FLOW003 | Pack 5, qty 25 — all four policies differ |
| FLOW004 | Pallet 100 + 135 units; remainder policies after crossdock |
| FLOW005 | Multi-line: 1125145 / 25 + 1000015 / 135 |
| FLOW006 | Same multi-line structure as FLOW005 |

Create payloads: [`data/postman_asns.json`](data/postman_asns.json). Postman notes: [`data/POSTMAN_README.md`](data/POSTMAN_README.md).

## Scripts

### 1. `create_asns.py` — create demo ASNs in MAWM

Posts each demo ASN individually to `/receiving/api/receiving/asn/save`.

```bash
python create_asns.py --all
python create_asns.py --asn FLOW001
python create_asns.py --all --token-file .token
python create_asns.py --dry-run --all
```

### 2. `run_flowthrough.py` — allocation engine

Fetches an ASN from MAWM, runs five allocation columns per line, and optionally creates replenishment orders.

```bash
# Preview all algorithms (no MAWM writes)
python run_flowthrough.py --mode preview

# Apply each line's part default and create orders
python run_flowthrough.py --mode apply --asn FLOW001
```

**Preview / comparison columns (per ASN line):**

1. Proportional — pallet pass (if applicable) + proportional remainder
2. Fixed facility priority — pallet pass + priority remainder
3. Largest shortage first — pallet pass + greedy by shortage
4. Weighted score — pallet pass + 70/30 score remainder
5. **Default** — same as whichever policy is set on the part (`default_algorithm` in config)

**Apply mode** uses each line's part **`default_algorithm`** automatically (no manual pick), then creates replenishment orders per destination after `YES` confirmation per line.

Multi-line ASNs (e.g. **FLOW005**, **FLOW006**) allocate each line independently; column 5 resolves to that line's part default.

See **[ALLOCATION.md](ALLOCATION.md)** for pallet pass, remainder logic, all four policies, and a **weighted score walkthrough** (FLOW001).

## Demo workflow

1. `python create_asns.py --all --token-file .token`
2. `python run_flowthrough.py --mode preview --asn FLOW001 --token-file .token`
3. Walk through **FLOW001**–**FLOW006** as in the table above
4. `python run_flowthrough.py --mode apply --asn FLOW001 --token-file .token` when ready to create orders

Order ids: `FLOW-{AsnId}-{DMx}` (e.g. `FLOW-FLOW001-DM2`).

## Web UI samples (static mockups)

Preview layout explorations — **no API, no Vercel**. Open [`samples/index.html`](samples/index.html) in a browser (FLOW005 hardcoded).

## Configuration

| File | Purpose |
|------|---------|
| `data/facility_inventory.json` | Inventory, pack/pallet, **`default_algorithm` per part** |
| `data/postman_asns.json` | ASN save payloads for create_asns / Postman |
| `data/postman_order_FLOW005.json` | Sample replenishment order payloads (Postman) |
| `ALLOCATION.md` | Policies, pallet/remainder logic, weighted score walkthrough (FLOW001) |
| `runs/` | Audit JSON from each run_flowthrough execution |

Edit `facility_inventory.json` to change max qty (set **max to 0** to exclude a facility from an item), available inventory, pack/pallet overrides, facility priority, and **`default_algorithm`** (`proportional`, `fixed_priority`, `largest_shortage`, `weighted_score`).

## Sample items

1000012, 1000013, 1000014, 1000015, 1000054, 1125145, 3000011, 3000014

## Authentication

Both scripts resolve a Bearer token **before** prompting for ASN.

**Token file** (recommended for long JWTs):

```powershell
# Save your access token as a single line in .token (gitignored)
python run_flowthrough.py --mode preview --token-file .token
```

**OAuth via environment variables:**

```powershell
$env:MANHATTAN_PASSWORD = "your_password"
$env:MANHATTAN_SECRET = "your_client_secret"
python run_flowthrough.py --mode preview
```

**Manual prompt** uses hidden input. Paste only the access token, not the word `Bearer`.
