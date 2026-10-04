# Fulfillment Hub (Python + Streamlit)

A simple fulfillment app for XYZ: order pipeline, priority handling, scan-to-pick checks,
Warehouse-2 stock moves, courier staging/handover, and an issue log. Uses dummy data.

## Run locally
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
Open http://localhost:8501. Use **Reset demo data** in the sidebar to start over
(or delete `fulfillment_data.json`).

## Demo flow (follow one order end to end)
1. **Dashboard** - see delayed / at-risk / priority orders.
2. **Office** - process a priority order (app suggests the earliest pickup), create label.
3. **Warehouse → PICK** - start the order marked "DO THIS ONE NEXT". Scan a *different variant*
   (see the Demo helper) to see the wrong-variant block. Then scan the right SKUs.
4. **Warehouse → PACK** - tick the checklist, move to staging.
5. **Staging & Pickup** - hand over by typing the order ID; try the wrong courier.
6. **Inventory** - mark the Warehouse-2 stock move as done for the order waiting for stock.
7. **Issues** - see auto-logged problems.

## Deploy (free)
Push to GitHub, then create an app on Streamlit Community Cloud pointing to `app.py`.
