# Flowthrough — Web App (Vercel)

**Version 1.0.0** — ASN-driven replenishment allocation against MAWM.

## Deploy to Vercel

Repository: [github.com/sidmsmith/flowthrough](https://github.com/sidmsmith/flowthrough)

### Environment variables

Same as Order Generator:

| Variable | Required |
|----------|----------|
| `MANHATTAN_PASSWORD` | Yes |
| `MANHATTAN_SECRET` | Yes |
| `MANHATTAN_USAGE_INGEST_URL` | Optional (usage dashboard) |

`MANHATTAN_USAGE_INGEST_SECRET` is **not** used by this app.

### URL parameters

| Parameter | Effect |
|-----------|--------|
| `Organization` | Pre-fill ORG and auto-authenticate |
| `Location` | Full facility id (e.g. `SS-DEMO-DM1`) for receiving location |
| `ASN`, `asn`, `AsnId`, etc. | Pre-fill ASN and auto-load after auth |

Example:

```
https://flowthrough.vercel.app/?Organization=SS-DEMO&Location=SS-DEMO-DM1&AsnId=ASNFLOW001
```

### Local dev

```bash
npm install
pip install -r requirements-vercel.txt
vercel dev
```

### Usage tracking (`flowthrough-app`)

Events sent to the apps dashboard when `MANHATTAN_USAGE_INGEST_URL` is set:

- `app_opened`
- `auth_attempt`, `auth_success`, `auth_failed`
- `load_asn_attempt`, `load_asn_completed`, `load_asn_failed`
- `create_orders_attempt`, `create_orders_completed`, `create_orders_failed`

### Project layout (web subset)

```
flowthrough/
├── index.html
├── public/
│   ├── app.js
│   ├── shared-ui.js
│   └── shared.css
├── api/index.py
├── allocation/
├── data/facility_inventory.json
├── flowthrough_service.py
├── mawm_client.py
├── config_loader.py
├── order_builder.py
├── vercel.json
├── server.js
└── package.json
```

CLI scripts (`run_flowthrough.py`, `samples/`) remain in the local workspace but are excluded from the GitHub deploy repo via `.gitignore`.
