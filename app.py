"""
Fulfillment Hub - a simple order-fulfillment app for a small e-commerce business (XYZ).

Run:  streamlit run app.py

Problems it tackles (from the brief):
  1. No at-a-glance order status        -> Dashboard + pipeline board
  2. Delays go unnoticed                -> per-stage time limits, "Delayed" / "At risk" alerts
  3. Priority orders get mixed up       -> priority always sorted first, shorter time limits
  4. Missing / wrong stock              -> shelf locations, Warehouse-2 transfers, scan-to-pick
  5. Wrong product or variant shipped   -> scan check at picking, wrong-variant is blocked + logged
  6. Misplaced boxes / missed pickup    -> courier lanes, pickup countdown, scan-to-handover
  7. Problems handled informally        -> Issue log with owner + status (auto-created too)

All data is dummy data, stored in fulfillment_data.json next to this file
(so the Office and Warehouse screens can be open on different devices/tabs).
"""

import itertools
import json
import os
import random
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Fulfillment Hub", page_icon="📦", layout="wide")

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fulfillment_data.json")

STAGES = ["Received", "Processed", "Picking", "Packing", "Staged", "Shipped"]
ACTIVE = ["Received", "Processed", "Picking", "Packing", "Staged"]

# Minutes an order may stay in a stage before it is flagged "Delayed" (priority orders get half).
STAGE_LIMIT = {"Received": 30, "Processed": 45, "Picking": 60, "Packing": 30}

# An order is "At risk" if the courier pickup is closer than this many minutes
# and the order is still in that stage.
RISK_BUFFER = {"Processed": 75, "Picking": 50, "Packing": 20}

LOW_STOCK = 5


# ----------------------------------------------------------------------------
# Time helpers
# ----------------------------------------------------------------------------
def now():
    return datetime.now().replace(microsecond=0)


def ts(dt):
    return dt.isoformat()


def parse(s):
    return datetime.fromisoformat(s)


def mins_since(s):
    return int((now() - parse(s)).total_seconds() // 60)


def mins_until(s):
    return int((parse(s) - now()).total_seconds() // 60)


def human(m):
    m = abs(int(m))
    h, mm = divmod(m, 60)
    return f"{h}h {mm}m" if h else f"{mm}m"


def round5(dt):
    return dt.replace(minute=(dt.minute // 5) * 5, second=0, microsecond=0)


# ----------------------------------------------------------------------------
# Dummy data
# ----------------------------------------------------------------------------
CATALOG = [
    ("TSH", "Cotton T-Shirt", [[("BLU", "Blue"), ("BLK", "Black")], [("M", "M"), ("L", "L")]]),
    ("HOD", "Zip Hoodie", [[("GRY", "Grey"), ("NVY", "Navy")], [("M", "M"), ("L", "L")]]),
    ("MUG", "Ceramic Mug", [[("WHT", "White"), ("BLK", "Black")]]),
    ("BTL", "Steel Bottle", [[("500", "500 ml"), ("750", "750 ml")]]),
    ("CAP", "Baseball Cap", [[("RED", "Red"), ("BLK", "Black")]]),
    ("TOT", "Canvas Tote", [[("NAT", "Natural"), ("BLK", "Black")]]),
    ("NTB", "A5 Notebook", [[("RUL", "Ruled"), ("PLN", "Plain")]]),
    ("CSE", "Phone Case", [[("I14", "iPhone 14"), ("I15", "iPhone 15")], [("CLR", "Clear"), ("BLK", "Black")]]),
]
CUSTOMERS = ["Aarav Shah", "Priya Nair", "Rohan Gupta", "Sneha Patil", "Vikram Rao", "Ananya Iyer",
             "Kabir Mehta", "Isha Verma", "Arjun Reddy", "Meera Kulkarni", "Dev Malhotra", "Tara Joshi"]
CHANNELS = ["Amazon", "Flipkart", "Meesho", "Own website"]


def seed():
    rnd = random.Random(7)
    t = now()

    products, stock = {}, {}
    for base, name, dims in CATALOG:
        for combo in itertools.product(*dims):
            sku = base + "-" + "-".join(c[0] for c in combo)
            products[sku] = {"name": name, "variant": ", ".join(c[1] for c in combo)}
    for i, sku in enumerate(products):
        aisle, bay, shelf = chr(65 + i // 6), i % 6 + 1, i % 3 + 1
        main = rnd.randint(0, 4) if i % 7 == 3 else rnd.randint(8, 40)
        stock[sku] = {"main": main, "loc": f"{aisle}-{bay:02d}-{shelf}",
                      "wh2": rnd.randint(10, 60), "wh2_loc": f"W2-R{i % 4 + 1}-{i % 5 + 1}"}

    couriers = {
        "SwiftEx": {"cost": 120, "speed": "Next day", "pickup": ts(round5(t + timedelta(minutes=70)))},
        "QuickShip": {"cost": 80, "speed": "2-3 days", "pickup": ts(round5(t + timedelta(minutes=150)))},
        "EcoPost": {"cost": 45, "speed": "4-5 days", "pickup": ts(round5(t + timedelta(minutes=240)))},
    }

    plan = (["Received"] * 8 + ["Processed"] * 8 + ["Picking"] * 5 + ["Packing"] * 4
            + ["Staged"] * 6 + ["Shipped"] * 5)
    ago = {"Received": (2, 25), "Processed": (5, 35), "Picking": (5, 40), "Packing": (5, 20),
           "Staged": (10, 60), "Shipped": (120, 300)}
    skus = list(products)
    orders = {}
    for i, status in enumerate(plan):
        oid = f"ORD-{1001 + i}"
        priority = rnd.random() < 0.25
        lines = []
        for sku in rnd.sample(skus, rnd.randint(1, 3)):
            qty = rnd.randint(1, 2)
            lines.append({"sku": sku, "qty": qty,
                          "picked": qty if status in ("Packing", "Staged", "Shipped") else 0})
        since = rnd.randint(*ago[status])
        courier = None
        if status != "Received":
            courier = "SwiftEx" if priority else rnd.choice(list(couriers))
        created = since + rnd.randint(10, 60)
        orders[oid] = {
            "id": oid, "channel": rnd.choice(CHANNELS), "customer": rnd.choice(CUSTOMERS),
            "priority": priority, "created": ts(t - timedelta(minutes=created)),
            "status": status, "status_since": ts(t - timedelta(minutes=since)),
            "courier": courier, "bay": f"{courier} lane" if status == "Staged" else None,
            "lines": lines,
            "history": [[ts(t - timedelta(minutes=created)), "Order received"],
                        [ts(t - timedelta(minutes=since)), f"Moved to {status}"]],
        }

    # --- Planted problems so the demo has something to show -------------------
    by_status = lambda s: [o for o in orders.values() if o["status"] == s]
    # (a) a priority order stuck in Picking for 95 minutes -> "Delayed"
    late = by_status("Picking")[0]
    late.update(priority=True, courier="SwiftEx", status_since=ts(t - timedelta(minutes=95)))
    # (b) an order whose stock is only in Warehouse 2 -> "Waiting for stock" + open transfer
    short = by_status("Processed")[0]
    short["lines"] = [{"sku": "HOD-GRY-L", "qty": 2, "picked": 0}]
    stock["HOD-GRY-L"]["main"] = 0
    transfers = [{"id": "TR-1", "sku": "HOD-GRY-L", "qty": 20, "status": "Open",
                  "created": ts(t - timedelta(minutes=12)), "for_order": short["id"]}]
    # (c) a priority order not yet picked with the SwiftEx pickup only 70 min away -> "At risk"
    risky = by_status("Processed")[1]
    risky.update(priority=True, courier="SwiftEx")
    # (d) a priority order that has sat in Received for 40 minutes -> "Delayed"
    first_new = by_status("Received")[0]
    first_new.update(priority=True, status_since=ts(t - timedelta(minutes=40)))

    issues = [{"id": "ISS-1", "time": ts(t - timedelta(minutes=30)), "order": short["id"],
               "type": "Stock missing on shelf", "detail": "HOD-GRY-L shelf empty, stock is in Warehouse 2",
               "owner": "Warehouse", "status": "Open"}]

    return {"products": products, "stock": stock, "couriers": couriers, "orders": orders,
            "transfers": transfers, "issues": issues}


def save(db):
    with open(DATA_FILE, "w") as f:
        json.dump(db, f, indent=1)


def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f:
                db = json.load(f)
            # Demo data is built around "today's" courier pickups. Once every pickup
            # has passed, the data is stale, so rebuild it (keeps a hosted demo fresh).
            if now() <= max(parse(c["pickup"]) for c in db["couriers"].values()):
                return db
        except Exception:
            pass
    db = seed()
    save(db)
    return db


# ----------------------------------------------------------------------------
# Business logic
# ----------------------------------------------------------------------------
def pname(db, sku):
    p = db["products"][sku]
    return f"{p['name']} - {p['variant']}"


def flash(kind, msg):
    st.session_state["flash"] = (kind, msg)


def show_flash():
    if "flash" in st.session_state:
        kind, msg = st.session_state.pop("flash")
        {"success": st.success, "error": st.error, "warning": st.warning}.get(kind, st.info)(msg)


def set_status(o, status):
    o["status"] = status
    o["status_since"] = ts(now())
    o["history"].append([ts(now()), f"Moved to {status}"])


def next_id(prefix, items, key="id"):
    nums = [int(i[key].split("-")[1]) for i in items if i[key].startswith(prefix)]
    return f"{prefix}-{max(nums) + 1 if nums else 1}"


def add_issue(db, order, typ, detail, owner="Office", status="Open"):
    db["issues"].append({"id": next_id("ISS", db["issues"]), "time": ts(now()), "order": order or "-",
                         "type": typ, "detail": detail, "owner": owner, "status": status})


def open_issue_orders(db):
    return {i["order"] for i in db["issues"] if i["status"] == "Open"}


def shortages(db, o):
    """Lines where main-warehouse stock is not enough for what is still to pick."""
    out = []
    for l in o["lines"]:
        left = l["qty"] - l["picked"]
        s = db["stock"][l["sku"]]
        if left > 0 and s["main"] < left:
            out.append((l["sku"], left, s["main"], s["wh2"]))
    return out


def ensure_transfer(db, o):
    """Create a Warehouse-2 -> main transfer for any shortage (or raise an out-of-stock issue)."""
    for sku, need, main, wh2 in shortages(db, o):
        already = any(t["sku"] == sku and t["for_order"] == o["id"] and t["status"] == "Open"
                      for t in db["transfers"])
        if already:
            continue
        if wh2 >= need - main:
            qty = min(wh2, max(need - main, 10))
            db["transfers"].append({"id": next_id("TR", db["transfers"]), "sku": sku, "qty": qty,
                                    "status": "Open", "created": ts(now()), "for_order": o["id"]})
        else:
            add_issue(db, o["id"], "Out of stock", f"{sku} not available in either warehouse", "Office")


def is_delayed(o):
    limit = STAGE_LIMIT.get(o["status"])
    if not limit:
        return False
    if o["priority"]:
        limit //= 2
    return mins_since(o["status_since"]) > limit


def at_risk(db, o):
    buf = RISK_BUFFER.get(o["status"])
    if not buf or not o["courier"]:
        return None
    m = mins_until(db["couriers"][o["courier"]]["pickup"])
    if m < 0:
        return "🚨 Missed pickup - reassign courier"
    if m < buf:
        return f"🚨 At risk: pickup in {human(m)}"
    return None


def alerts(db, o):
    a = []
    if o["status"] == "Shipped":
        return a
    if is_delayed(o):
        a.append(f"⏱ Delayed ({human(mins_since(o['status_since']))} in {o['status']})")
    r = at_risk(db, o)
    if r:
        a.append(r)
    if o["status"] in ("Processed", "Picking") and shortages(db, o):
        a.append("📉 Waiting for stock")
    if o["id"] in open_issue_orders(db):
        a.append("🚩 Open issue")
    return a


def pickup_label(db, courier):
    if not courier:
        return "-"
    m = mins_until(db["couriers"][courier]["pickup"])
    return human(m) if m >= 0 else f"passed {human(m)} ago"


def recommend_courier(db, o):
    options = [(n, c) for n, c in db["couriers"].items() if mins_until(c["pickup"]) >= 20]
    if not options:
        return list(db["couriers"])[0]
    if o["priority"]:
        return min(options, key=lambda x: x[1]["pickup"])[0]       # earliest pickup
    return min(options, key=lambda x: x[1]["cost"])[0]              # cheapest


def sort_key(db, o):
    c = o["courier"]
    pickup = db["couriers"][c]["pickup"] if c else "9999"
    return (not o["priority"], pickup, o["created"])


def order_df(db, orders):
    rows = []
    for o in orders:
        rows.append({
            "Order": o["id"], "⚡": "⚡" if o["priority"] else "", "Status": o["status"],
            "Customer": o["customer"], "Courier": o["courier"] or "-",
            "Pickup in": pickup_label(db, o["courier"]),
            "Time in stage": human(mins_since(o["status_since"])),
            "Alerts": " | ".join(alerts(db, o)),
        })
    return pd.DataFrame(rows)


def show_table(df):
    if df.empty:
        st.info("Nothing here.")
        return
    styled = df.style.apply(
        lambda r: ["background-color: rgba(255, 75, 75, 0.25)" if r.get("Alerts") else ""] * len(r), axis=1)
    st.dataframe(styled, width="stretch", hide_index=True)


def label_html(db, o):
    rows = "".join(f"<tr><td>{pname(db, l['sku'])}</td><td>{l['sku']}</td><td>x{l['qty']}</td></tr>"
                   for l in o["lines"])
    c = db["couriers"][o["courier"]]
    pr = "<h2 style='color:#c00'>⚡ PRIORITY - SHIP TODAY</h2>" if o["priority"] else ""
    return f"""<html><body style="font-family:monospace;border:3px solid #000;padding:16px;width:420px">
<h1 style="margin:0">{o['id']}</h1>{pr}
<p><b>Ship to:</b> {o['customer']}<br><b>Channel:</b> {o['channel']}</p>
<p><b>Courier:</b> {o['courier']} ({c['speed']})<br><b>Pickup:</b> {parse(c['pickup']).strftime('%I:%M %p')}</p>
<table border="1" cellpadding="4" style="border-collapse:collapse;width:100%">{rows}</table>
</body></html>"""


# ----------------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------------
def page_dashboard(db):
    st.header("📊 Dashboard")
    active = [o for o in db["orders"].values() if o["status"] in ACTIVE]
    delayed = [o for o in active if is_delayed(o)]
    risky = [o for o in active if at_risk(db, o)]
    prio = [o for o in active if o["priority"]]
    open_iss = [i for i in db["issues"] if i["status"] == "Open"]
    open_tr = [t for t in db["transfers"] if t["status"] == "Open"]

    c = st.columns(6)
    c[0].metric("Active orders", len(active))
    c[1].metric("⚡ Priority open", len(prio))
    c[2].metric("⏱ Delayed", len(delayed))
    c[3].metric("🚨 Pickup at risk", len(risky))
    c[4].metric("🚩 Open issues", len(open_iss))
    c[5].metric("🔁 Stock moves pending", len(open_tr))

    st.subheader("Orders by stage")
    counts = pd.DataFrame(
        {"Orders": [sum(1 for o in db["orders"].values() if o["status"] == s) for s in STAGES]},
        index=STAGES)
    st.bar_chart(counts)

    st.subheader("🔥 Needs attention now")
    flagged = sorted([o for o in active if alerts(db, o)], key=lambda o: sort_key(db, o))
    show_table(order_df(db, flagged))

    with st.expander("All active orders", expanded=False):
        status = st.multiselect("Filter by stage", ACTIVE, default=ACTIVE)
        rows = sorted([o for o in active if o["status"] in status], key=lambda o: sort_key(db, o))
        show_table(order_df(db, rows))

    low = [(s, pname(db, s), v["main"], v["wh2"]) for s, v in db["stock"].items() if v["main"] < LOW_STOCK]
    if low:
        st.subheader("📉 Low stock in main warehouse")
        st.dataframe(pd.DataFrame(low, columns=["SKU", "Product", "Main", "Warehouse 2"]),
                     width="stretch", hide_index=True)


def page_office(db):
    st.header("📝 Office - process new orders")
    st.caption("Priority orders are listed first. Pick a courier, then create the label. "
               "The app suggests the earliest pickup for priority orders and the cheapest for the rest.")

    new = sorted([o for o in db["orders"].values() if o["status"] == "Received"],
                 key=lambda o: (not o["priority"], o["created"]))
    if not new:
        st.success("All orders are processed 🎉")
    for o in new:
        with st.container(border=True):
            a, b, c = st.columns([3, 4, 3])
            a.markdown(f"### {o['id']} {'⚡' if o['priority'] else ''}")
            a.caption(f"{o['customer']} · {o['channel']}")
            if is_delayed(o):
                a.error(f"⏱ Waiting {human(mins_since(o['status_since']))}")
            b.markdown("**Items**")
            for l in o["lines"]:
                s = db["stock"][l["sku"]]
                warn = " ⚠️ low in main" if s["main"] < l["qty"] else ""
                b.write(f"{l['qty']} × {pname(db, l['sku'])} (`{l['sku']}`){warn}")
            names = list(db["couriers"])
            rec = recommend_courier(db, o)
            choice = c.selectbox(
                "Courier", names, index=names.index(rec), key=f"cour_{o['id']}",
                format_func=lambda n: f"{n} · ₹{db['couriers'][n]['cost']} · {db['couriers'][n]['speed']} · "
                                      f"pickup in {pickup_label(db, n)}")
            if mins_until(db["couriers"][choice]["pickup"]) < 20:
                c.warning("Pickup is very close or passed.")
            if c.button("Create label & send to warehouse", key=f"proc_{o['id']}", type="primary"):
                o["courier"] = choice
                set_status(o, "Processed")
                ensure_transfer(db, o)
                save(db)
                flash("success", f"{o['id']} processed. Label ready in the Warehouse queue.")
                st.rerun()

    st.divider()
    with st.expander("🖨️ Re-print a label"):
        done = [o["id"] for o in db["orders"].values() if o["courier"]]
        pick = st.selectbox("Order", done)
        if pick:
            st.download_button("Download label (HTML)", label_html(db, db["orders"][pick]),
                               file_name=f"label_{pick}.html", mime="text/html")

    with st.expander("➕ Add an order manually"):
        with st.form("new_order", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            cust = c1.text_input("Customer name")
            chan = c2.selectbox("Channel", CHANNELS)
            prio = c3.checkbox("⚡ Priority (same day)")
            skus = ["-"] + list(db["products"])
            fmt = lambda s: "-" if s == "-" else f"{s} · {pname(db, s)}"
            picks = []
            for i in range(3):
                x, y = st.columns([4, 1])
                picks.append((x.selectbox(f"Item {i + 1}", skus, key=f"ni{i}", format_func=fmt),
                              y.number_input("Qty", 1, 20, 1, key=f"nq{i}")))
            if st.form_submit_button("Add order"):
                lines = [{"sku": s, "qty": int(q), "picked": 0} for s, q in picks if s != "-"]
                if not cust or not lines:
                    st.error("Enter a customer and at least one item.")
                else:
                    oid = next_id("ORD", list(db["orders"].values()))
                    db["orders"][oid] = {
                        "id": oid, "channel": chan, "customer": cust, "priority": prio,
                        "created": ts(now()), "status": "Received", "status_since": ts(now()),
                        "courier": None, "bay": None, "lines": lines,
                        "history": [[ts(now()), "Order received"]]}
                    save(db)
                    flash("success", f"{oid} added.")
                    st.rerun()


def handle_scan(db, o, code):
    code = code.strip().upper()
    todo = [l for l in o["lines"] if l["picked"] < l["qty"]]
    match = [l for l in todo if l["sku"] == code]
    if match:
        l = match[0]
        s = db["stock"][code]
        if s["main"] <= 0:
            flash("error", f"System shows 0 of {code} on the shelf. Press 'Not on shelf'.")
            return
        s["main"] -= 1
        l["picked"] += 1
        flash("success", f"✅ Correct: {pname(db, code)}")
        if all(x["picked"] >= x["qty"] for x in o["lines"]):
            set_status(o, "Packing")
            st.session_state.pop("active_pick", None)
            flash("success", f"✅ All items for {o['id']} picked. Take the basket to the PACK tab.")
    elif code in [l["sku"] for l in o["lines"]]:
        flash("warning", "You already picked all units of that item.")
    elif code in db["products"]:
        same_family = [l["sku"] for l in todo if l["sku"].split("-")[0] == code.split("-")[0]]
        if same_family:
            flash("error", f"❌ WRONG VARIANT. You scanned {pname(db, code)}. "
                           f"This order needs {pname(db, same_family[0])}. Put it back.")
            add_issue(db, o["id"], "Wrong variant caught at picking",
                      f"Scanned {code}, needed {same_family[0]}", "Warehouse", status="Resolved")
        else:
            flash("error", f"❌ WRONG PRODUCT. {pname(db, code)} is not part of this order.")
            add_issue(db, o["id"], "Wrong item caught at picking", f"Scanned {code}",
                      "Warehouse", status="Resolved")
    else:
        flash("error", f"Code '{code}' not recognised. Try again.")
    save(db)


def pick_screen(db, o):
    st.subheader(f"Picking {o['id']} {'⚡ PRIORITY' if o['priority'] else ''}")
    st.caption(f"Courier: {o['courier']} · pickup in {pickup_label(db, o['courier'])}")
    for l in o["lines"]:
        left = l["qty"] - l["picked"]
        s = db["stock"][l["sku"]]
        with st.container(border=True):
            a, b, c, d = st.columns([4, 2, 2, 2])
            a.markdown(f"**{pname(db, l['sku'])}**  \n`{l['sku']}`")
            b.markdown(f"📍 Shelf **{s['loc']}**")
            c.markdown(f"{'✅' if left == 0 else '🟡'} **{l['picked']} / {l['qty']}**")
            if left > 0 and d.button("Not on shelf", key=f"nos_{o['id']}_{l['sku']}"):
                s["main"] = 0
                add_issue(db, o["id"], "Stock missing on shelf",
                          f"{l['sku']} not found at {s['loc']} while picking", "Warehouse")
                ensure_transfer(db, o)
                save(db)
                st.session_state.pop("active_pick", None)
                flash("warning", "Reported. Office is alerted and a stock move from Warehouse 2 was requested.")
                st.rerun()
    with st.form("scan_form", clear_on_submit=True):
        code = st.text_input("Scan or type the item code", placeholder="e.g. TSH-BLU-M")
        go = st.form_submit_button("✔ Confirm item", type="primary")
    if go and code:
        handle_scan(db, o, code)
        st.rerun()
    if st.button("← Back to queue"):
        st.session_state.pop("active_pick", None)
        st.rerun()
    with st.expander("Demo helper - SKUs for this order"):
        st.write(", ".join(f"`{l['sku']}`" for l in o["lines"]))
        st.caption("Try scanning a different variant of the same product to see the wrong-variant check.")


def page_warehouse(db):
    st.header("📦 Warehouse - pick & pack")
    tab_pick, tab_pack = st.tabs(["1️⃣ PICK", "2️⃣ PACK"])

    with tab_pick:
        active = st.session_state.get("active_pick")
        ao = db["orders"].get(active) if active else None
        if ao and ao["status"] in ("Processed", "Picking") and not shortages(db, ao):
            pick_screen(db, ao)
        else:
            st.session_state.pop("active_pick", None)
            queue = sorted([o for o in db["orders"].values() if o["status"] in ("Processed", "Picking")],
                           key=lambda o: sort_key(db, o))
            if not queue:
                st.success("Nothing to pick right now.")
            first = True
            for o in queue:
                short = shortages(db, o)
                with st.container(border=True):
                    a, b, c = st.columns([3, 4, 3])
                    tag = "⚡ PRIORITY " if o["priority"] else ""
                    a.markdown(f"### {tag}{o['id']}")
                    a.caption(f"{o['courier']} · pickup in {pickup_label(db, o['courier'])}")
                    if first and not short:
                        a.success("▶ DO THIS ONE NEXT")
                    for al in alerts(db, o):
                        if "issue" not in al:
                            a.warning(al)
                    for l in o["lines"]:
                        b.write(f"{l['qty'] - l['picked']} × {pname(db, l['sku'])} · "
                                f"📍 {db['stock'][l['sku']]['loc']}")
                    if short:
                        c.error("Stock not in main warehouse")
                        has_tr = any(t["for_order"] == o["id"] and t["status"] == "Open"
                                     for t in db["transfers"])
                        if has_tr:
                            c.info("Stock move requested. Waiting for Warehouse 2.")
                        elif c.button("Request stock move", key=f"rq_{o['id']}"):
                            ensure_transfer(db, o)
                            save(db)
                            st.rerun()
                    else:
                        first = False
                        if c.button("Start picking", key=f"start_{o['id']}", type="primary"):
                            if o["status"] == "Processed":
                                set_status(o, "Picking")
                            st.session_state["active_pick"] = o["id"]
                            save(db)
                            st.rerun()

    with tab_pack:
        packing = sorted([o for o in db["orders"].values() if o["status"] == "Packing"],
                         key=lambda o: sort_key(db, o))
        if not packing:
            st.info("No orders waiting to be packed.")
        for o in packing:
            with st.container(border=True):
                a, b = st.columns([3, 5])
                a.markdown(f"### {'⚡ ' if o['priority'] else ''}{o['id']}")
                a.caption(f"{o['courier']} · pickup in {pickup_label(db, o['courier'])}")
                for al in alerts(db, o):
                    a.warning(al)
                a.download_button("🖨️ Print label", label_html(db, o), file_name=f"label_{o['id']}.html",
                                  mime="text/html", key=f"lbl_{o['id']}")
                checks = [b.checkbox(f"{l['qty']} × {pname(db, l['sku'])} is in the box",
                                     key=f"pk_{o['id']}_{l['sku']}") for l in o["lines"]]
                checks.append(b.checkbox("Label is stuck on the box", key=f"pkl_{o['id']}"))
                if b.button("Done → move to staging", key=f"pack_{o['id']}", type="primary",
                            disabled=not all(checks)):
                    o["bay"] = f"{o['courier']} lane"
                    set_status(o, "Staged")
                    save(db)
                    flash("success", f"{o['id']} packed. Put the box in the '{o['bay']}'.")
                    st.rerun()


def page_staging(db):
    st.header("🚚 Staging & courier pickup")
    st.caption("Each courier has its own lane. Scan a box when handing it over - "
               "the app blocks boxes given to the wrong courier.")
    for cname, c in db["couriers"].items():
        mine = [o for o in db["orders"].values() if o["courier"] == cname and o["status"] in
                ("Processed", "Picking", "Packing", "Staged")]
        mine.sort(key=lambda o: sort_key(db, o))
        staged = [o for o in mine if o["status"] == "Staged"]
        not_ready = [o for o in mine if o["status"] != "Staged"]
        m = mins_until(c["pickup"])
        when = f"in {human(m)}" if m >= 0 else f"overdue by {human(m)}"
        with st.container(border=True):
            st.subheader(f"{cname} · pickup {parse(c['pickup']).strftime('%I:%M %p')} ({when})")
            st.progress(len(staged) / len(mine) if mine else 1.0,
                        text=f"{len(staged)} of {len(mine)} boxes ready in lane")
            if not_ready and m < 30:
                st.error(f"{len(not_ready)} order(s) NOT ready and pickup is close: "
                         + ", ".join(o["id"] for o in not_ready))
            if mine:
                show_table(order_df(db, mine))

            col1, col2 = st.columns(2)
            with col1:
                with st.form(f"hand_{cname}", clear_on_submit=True):
                    code = st.text_input("Scan box label to hand over", placeholder="e.g. ORD-1030")
                    if st.form_submit_button("Hand over box"):
                        oid = code.strip().upper()
                        oid = f"ORD-{oid}" if oid.isdigit() else oid
                        o = db["orders"].get(oid)
                        if not o:
                            flash("error", f"Box '{code}' not found.")
                        elif o["status"] == "Shipped":
                            flash("warning", f"{oid} was already handed over.")
                        elif o["status"] != "Staged":
                            flash("error", f"{oid} is not packed yet (status: {o['status']}).")
                        elif o["courier"] != cname:
                            flash("error", f"❌ WRONG COURIER. {oid} belongs to {o['courier']}, not {cname}.")
                            add_issue(db, oid, "Box in wrong courier lane", f"Scanned at {cname} handover",
                                      "Warehouse", status="Resolved")
                        else:
                            set_status(o, "Shipped")
                            flash("success", f"{oid} handed to {cname}.")
                        save(db)
                        st.rerun()
                if staged and st.button("Hand over ALL staged boxes", key=f"all_{cname}"):
                    for o in staged:
                        set_status(o, "Shipped")
                    save(db)
                    flash("success", f"{len(staged)} boxes handed to {cname}.")
                    st.rerun()
            with col2:
                if staged:
                    with st.expander("Can't find a box?"):
                        pick = st.selectbox("Order", [o["id"] for o in staged], key=f"lost_{cname}")
                        if st.button("Report missing box", key=f"lostb_{cname}"):
                            add_issue(db, pick, "Packed box misplaced", f"Not found in {cname} lane", "Warehouse")
                            save(db)
                            flash("warning", "Reported in the Issue log.")
                            st.rerun()
                if not_ready:
                    with st.expander("Move a not-ready order to a later courier"):
                        pick = st.selectbox("Order", [o["id"] for o in not_ready], key=f"mv_{cname}")
                        later = [n for n, x in db["couriers"].items()
                                 if n != cname and mins_until(x["pickup"]) > m]
                        if later:
                            tgt = st.selectbox("New courier", later, key=f"mvt_{cname}")
                            if st.button("Move", key=f"mvb_{cname}"):
                                db["orders"][pick]["courier"] = tgt
                                db["orders"][pick]["history"].append([ts(now()), f"Courier changed to {tgt}"])
                                save(db)
                                st.rerun()
                        else:
                            st.write("No later courier today.")


def page_inventory(db):
    st.header("🏬 Inventory & stock moves")
    t1, t2 = st.tabs(["Stock", "Moves from Warehouse 2"])
    with t1:
        q = st.text_input("Search SKU or product")
        rows = []
        for sku, s in db["stock"].items():
            name = pname(db, sku)
            if q and q.lower() not in (sku + name).lower():
                continue
            rows.append({"SKU": sku, "Product": name, "Main qty": s["main"], "Shelf": s["loc"],
                         "Warehouse 2 qty": s["wh2"], "WH2 location": s["wh2_loc"],
                         "Status": "⚠️ Low" if s["main"] < LOW_STOCK else "OK"})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        with st.expander("Correct a stock count (after a physical check)"):
            with st.form("adjust"):
                sku = st.selectbox("SKU", list(db["stock"]), format_func=lambda s: f"{s} · {pname(db, s)}")
                new = st.number_input("Counted quantity on shelf", 0, 1000, 0)
                if st.form_submit_button("Update"):
                    old = db["stock"][sku]["main"]
                    db["stock"][sku]["main"] = int(new)
                    add_issue(db, None, "Stock count corrected", f"{sku}: {old} → {int(new)}",
                              "Warehouse", "Resolved")
                    save(db)
                    st.rerun()
    with t2:
        open_tr = [t for t in db["transfers"] if t["status"] == "Open"]
        if not open_tr:
            st.success("No pending stock moves.")
        for t in open_tr:
            with st.container(border=True):
                a, b, c = st.columns([4, 3, 2])
                a.markdown(f"**{pname(db, t['sku'])}** (`{t['sku']}`)")
                b.write(f"Move **{t['qty']}** from {db['stock'][t['sku']]['wh2_loc']} → main shelf "
                        f"{db['stock'][t['sku']]['loc']}  \nFor {t['for_order']}")
                if c.button("✔ Mark as moved", key=f"mv_{t['id']}", type="primary"):
                    s = db["stock"][t["sku"]]
                    qty = min(t["qty"], s["wh2"])
                    s["wh2"] -= qty
                    s["main"] += qty
                    t["status"] = "Done"
                    for i in db["issues"]:
                        if i["status"] == "Open" and i["order"] == t["for_order"] and "Stock missing" in i["type"]:
                            i["status"] = "Resolved"
                    save(db)
                    flash("success", f"Moved {qty} units. The order can now be picked.")
                    st.rerun()
        with st.expander("Request a move manually"):
            with st.form("newtr"):
                sku = st.selectbox("SKU", list(db["stock"]), format_func=lambda s: f"{s} · {pname(db, s)}")
                qty = st.number_input("Quantity", 1, 500, 10)
                if st.form_submit_button("Create request"):
                    db["transfers"].append({"id": next_id("TR", db["transfers"]), "sku": sku, "qty": int(qty),
                                            "status": "Open", "created": ts(now()), "for_order": "-"})
                    save(db)
                    st.rerun()


def page_issues(db):
    st.header("⚠️ Issue log")
    st.caption("Every problem gets an owner and a status, so nothing is forgotten. "
               "The app also logs some automatically.")
    with st.expander("➕ Report a problem", expanded=False):
        with st.form("newissue", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            order = c1.selectbox("Order (optional)", ["-"] + list(db["orders"]))
            typ = c2.selectbox("Type", ["Wrong item shipped", "Damaged item", "Stock missing on shelf",
                                        "Packed box misplaced", "Courier missed pickup", "Customer change",
                                        "Other"])
            owner = c3.selectbox("Owner", ["Office", "Warehouse", "Manager"])
            detail = st.text_input("What happened?")
            if st.form_submit_button("Log issue") and detail:
                add_issue(db, order, typ, detail, owner)
                save(db)
                st.rerun()

    open_i = [i for i in db["issues"] if i["status"] == "Open"]
    st.subheader(f"Open ({len(open_i)})")
    if not open_i:
        st.success("No open issues.")
    for i in reversed(open_i):
        with st.container(border=True):
            a, b, c = st.columns([5, 2, 2])
            a.markdown(f"**{i['type']}** · {i['order']}  \n{i['detail']}")
            b.write(f"Owner: **{i['owner']}**  \n{human(mins_since(i['time']))} ago")
            if c.button("Mark resolved", key=f"res_{i['id']}"):
                i["status"] = "Resolved"
                save(db)
                st.rerun()
    done = [i for i in db["issues"] if i["status"] == "Resolved"]
    with st.expander(f"Resolved ({len(done)})"):
        if done:
            st.dataframe(pd.DataFrame(done)[["id", "time", "order", "type", "detail", "owner"]],
                         width="stretch", hide_index=True)


# ----------------------------------------------------------------------------
# App shell
# ----------------------------------------------------------------------------
st.markdown("""<style>
.stButton>button, .stDownloadButton>button {min-height: 2.8rem; font-size: 1.05rem;}
</style>""", unsafe_allow_html=True)

PAGES = {
    "📊 Dashboard": page_dashboard,
    "📝 Office": page_office,
    "📦 Warehouse": page_warehouse,
    "🚚 Staging & Pickup": page_staging,
    "🏬 Inventory": page_inventory,
    "⚠️ Issues": page_issues,
}

db = load_db()

with st.sidebar:
    st.title("📦 Fulfillment Hub")
    st.caption("XYZ order fulfillment · demo data")
    page = st.radio("Go to", list(PAGES), label_visibility="collapsed")
    st.divider()
    st.caption(f"Time now: {now().strftime('%I:%M %p')}")
    if st.button("🔄 Refresh"):
        st.rerun()
    with st.expander("Reset demo"):
        if st.button("Reset demo data"):
            db = seed()
            save(db)
            st.session_state.clear()
            st.rerun()

show_flash()
PAGES[page](db)
