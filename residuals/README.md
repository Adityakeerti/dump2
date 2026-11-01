# Residuals: retired single-file UIs

These HTML pages were the per-service demo UIs before the React operations dashboard
(`../dashboard/`) replaced them. They are kept for reference only. No service serves them any more,
except `mesh_messenger.ui.html`, which `scripts/mesh_server.py` still serves to phones on the offline mesh.

| File | Was | Replaced by (dashboard page) |
|---|---|---|
| `UI.html` | unified live demo, served by agent_service at `/` and `/agent/ui` | Dashboard, Messages |
| `UI.legacy.html` | "Integrated User Islands" prototype | – |
| `agent_service.UI.html` | voice agent Ask Tab | Messages |
| `complaint_module.UI.html` | complaint escalation UI (`complaint_module/static/UI.html`) | TownHall |
| `emergency_routing.ui.html` | live map / CCTV / route commitment UI | Tickets |
| `mesh_messenger.ui.html` | offline mesh messenger (was `Project/ui.html`) | still served by `scripts/mesh_server.py` |
| `core_static_mesh.ui.html` | identical copy core served at `/ui.html` (`core/src/main/resources/static/`) | core no longer serves it |
