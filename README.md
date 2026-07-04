# Flowthrough — ASN-Driven Replenishment Demo



CLI tools for demonstrating ASN-driven replenishment and crossdock allocation against the MAWM demo environment (`salep.sce.manh.com`).



Simulated multi-facility inventory lives in a local JSON file (`data/facility_inventory.json`). Destination facilities use org-relative IDs (`DM2`–`DM5` → `{ORG}-DM2`, etc.).



## Setup



```bash

cd flowthrough

pip install -r requirements.txt

```



## Scripts



### 1. `create_asns.py` — create demo ASNs in MAWM



Posts each demo ASN individually to `/receiving/api/receiving/asn/save`.



```bash

python create_asns.py --all

python create_asns.py --asn ASNFLOW001

python create_asns.py --all --token-file .token

python create_asns.py --dry-run --all

```



Demo ASN ids: **ASNFLOW001** through **ASNFLOW005** (filter in MAWM: `AsnId like 'ASNFLOW%'`).



### 2. `run_flowthrough.py` — allocation engine



Fetches an ASN from MAWM, runs five allocation columns per line, and optionally creates replenishment orders.



```bash

# Preview all algorithms (no MAWM writes)

python run_flowthrough.py --mode preview



# Apply each line's part default and create orders

python run_flowthrough.py --mode apply --asn ASNFLOW001

```



**Preview / comparison columns (per ASN line):**



1. Proportional — pallet pass (if applicable) + proportional remainder

2. Fixed facility priority — pallet pass + priority remainder

3. Largest shortage first — pallet pass + greedy by shortage

4. Weighted score — pallet pass + 70/30 score remainder

5. **Default** — same as whichever policy is set on the part (`default_algorithm` in config)



**Apply mode** uses each line's part **`default_algorithm`** automatically (no manual pick), then creates replenishment orders per destination after `YES` confirmation per line.



Multi-line ASNs (e.g. **ASNFLOW005**) allocate each line independently; column 5 resolves to that line's part default.



See **[ALLOCATION.md](ALLOCATION.md)** for pallet pass, remainder logic, all four policies, and a **weighted score walkthrough** (ASNFLOW001).



## Demo workflow



1. `python create_asns.py --all --token-file .token`

2. `python run_flowthrough.py --mode preview --asn ASNFLOW001 --token-file .token`

3. **ASNFLOW001** — compare proportional vs fixed priority (cols 1 vs 2)

4. **ASNFLOW002** — qty 60 — all four policies differ

5. **ASNFLOW003** — pack 5, qty 25 — all four policies differ

6. **ASNFLOW004** — pallet 100 + 135 units; compare remainder policies after crossdock

7. **ASNFLOW005** — multi-line: **1125145** / 25 (same 4-way pack split as 003) + **1000015** / 135 (pallet demo)

8. `python run_flowthrough.py --mode apply --asn ASNFLOW001 --token-file .token` when ready to create orders

## Web UI samples (static mockups)

Preview layout explorations for a future web app — **no API, no Vercel**. Open [`samples/index.html`](samples/index.html) in a browser (ASNFLOW005 hardcoded).

## Configuration



| File | Purpose |

|------|---------|

| `data/facility_inventory.json` | Inventory, pack/pallet, **`default_algorithm` per part** |

| `data/postman_asns.json` | ASN save payloads for create_asns / Postman |

| `ALLOCATION.md` | Policies, pallet/remainder logic, weighted score walkthrough (ASNFLOW001) |

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

