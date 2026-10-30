#!/usr/bin/env python3
"""
Vehicle Detection Review Dashboard
Browse and correct OCR vehicle classifications from the code-enforcement service.
"""

import base64
import io
import json
import os
import sqlite3
from datetime import date, datetime, timedelta

import imagehash
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
import paho.mqtt.client as mqtt
from PIL import Image

# ── Config ────────────────────────────────────────────────────────────────────

DB_PATH      = os.getenv("DB_PATH",      "/data/code_enforcement.db")
FRIGATE_URL  = os.getenv("FRIGATE_URL",  "http://192.168.68.142:5050")
THUMB_DIR    = os.getenv("THUMB_DIR",    "/data/thumbnails")
MQTT_HOST    = os.getenv("MQTT_HOST",    "192.168.68.3")
MQTT_PORT    = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER    = os.getenv("MQTT_USER",    "addons")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

CATEGORIES = ["", "code_enforcement", "usps", "fedex", "ups", "amazon", "my_vehicle", "other", "false_positive"]

CATEGORY_COLORS = {
    "code_enforcement": "#ef4444",
    "usps":             "#3b82f6",
    "fedex":            "#8b5cf6",
    "ups":              "#f59e0b",
    "amazon":           "#10b981",
    "my_vehicle":       "#0ea5e9",
    "other":            "#6b7280",
    "false_positive":   "#d1d5db",
    "unclassified":     "#e5e7eb",
}

# ── DB ────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    for col_def in ["user_category TEXT", "reviewed INTEGER DEFAULT 0",
                     "claude_suggestion TEXT", "claude_confidence REAL", "claude_notes TEXT"]:
        try:
            conn.execute(f"ALTER TABLE detections ADD COLUMN {col_def}")
        except Exception:
            pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS known_vehicles (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            phash      TEXT NOT NULL,
            event_id   TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def fetch_thumbnail(event_id: str):
    """Fetch thumbnail image from Frigate. Returns PIL Image or None."""
    url = f"{FRIGATE_URL}/api/events/{event_id}/thumbnail.jpg"
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception:
        return None


def save_known_vehicle(conn, event_id: str):
    """Compute pHash for event thumbnail and store in known_vehicles."""
    img = fetch_thumbnail(event_id)
    if img is None:
        return False
    h = str(imagehash.phash(img))
    conn.execute(
        "INSERT INTO known_vehicles (phash, event_id, created_at) VALUES (?,?,?)",
        (h, event_id, datetime.utcnow().isoformat())
    )
    conn.commit()
    return True


def load_known_vehicles(conn) -> pd.DataFrame:
    rows = conn.execute(
        "SELECT id, event_id, created_at FROM known_vehicles ORDER BY created_at DESC"
    ).fetchall()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def load_detections(conn, start_date, end_date, cat_filter, reviewed_filter):
    wheres = ["date BETWEEN ? AND ?"]
    params = [start_date.isoformat(), end_date.isoformat()]

    if cat_filter == "All (excl. known)":
        # hide my_vehicle and false_positive from default view
        wheres.append("(user_category IS NULL OR user_category NOT IN ('my_vehicle', 'false_positive'))")
    elif cat_filter == "Unclassified only":
        wheres.append("(category IS NULL AND user_category IS NULL)")
    elif cat_filter == "Needs review":
        wheres.append("(reviewed = 0 OR reviewed IS NULL)")
    elif cat_filter not in ("All", ""):
        wheres.append("(user_category = ? OR (user_category IS NULL AND category = ?))")
        params += [cat_filter, cat_filter]

    if reviewed_filter == "Reviewed":
        wheres.append("reviewed = 1")
    elif reviewed_filter == "Not reviewed":
        wheres.append("(reviewed = 0 OR reviewed IS NULL)")

    sql = f"""
        SELECT
            id,
            timestamp,
            date,
            event_id,
            category,
            user_category,
            reviewed,
            matched_text,
            all_ocr_text,
            car_confidence,
            snapshot_url
        FROM detections
        WHERE {' AND '.join(wheres)}
        ORDER BY timestamp DESC
    """
    rows = conn.execute(sql, params).fetchall()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def today_count(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM detections WHERE date = ?", (date.today().isoformat(),)
    ).fetchone()[0]


def ce_count(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM detections WHERE user_category='code_enforcement' OR (user_category IS NULL AND category='code_enforcement')"
    ).fetchone()[0]


def unclassified_count(conn):
    return conn.execute(
        "SELECT COUNT(*) FROM detections WHERE category IS NULL AND user_category IS NULL"
    ).fetchone()[0]


def total_count(conn):
    return conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]


def load_claude_suggestions(conn) -> pd.DataFrame:
    """Rows Claude reviewed and proposed an actual category for, still awaiting human approval."""
    rows = conn.execute("""
        SELECT id, timestamp, event_id, claude_suggestion, claude_confidence, claude_notes
        FROM detections
        WHERE claude_suggestion IS NOT NULL
          AND user_category IS NULL
          AND (reviewed = 0 OR reviewed IS NULL)
        ORDER BY claude_confidence DESC, timestamp DESC
    """).fetchall()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


def load_claude_notes_only(conn) -> pd.DataFrame:
    """Rows Claude looked at but didn't have enough confidence to suggest a category for —
    context for a human to judge, not something to mass-approve."""
    rows = conn.execute("""
        SELECT id, timestamp, event_id, claude_notes
        FROM detections
        WHERE claude_notes IS NOT NULL
          AND claude_suggestion IS NULL
          AND user_category IS NULL
          AND (reviewed = 0 OR reviewed IS NULL)
        ORDER BY timestamp DESC
    """).fetchall()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()


# ── MQTT ─────────────────────────────────────────────────────────────────────

def republish_ce_alert(row: pd.Series):
    try:
        client = mqtt.Client(client_id="vehicle-dashboard")
        if MQTT_PASSWORD:
            client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
        client.connect(MQTT_HOST, MQTT_PORT, 10)

        now = datetime.utcnow().isoformat()
        payload = {
            "event_id":       row.get("event_id", ""),
            "category":       "code_enforcement",
            "label":          "Code Enforcement",
            "matched_text":   "human-tagged",
            "snapshot_url":   row.get("snapshot_url", ""),
            "timestamp":      now,
            "human_corrected": True,
        }
        client.publish("code_enforcement/alert", json.dumps(payload))

        # Update retained counts
        conn = get_conn()
        today_ce = conn.execute(
            "SELECT COUNT(*) FROM detections WHERE date=? AND (user_category='code_enforcement' OR (user_category IS NULL AND category='code_enforcement'))",
            (date.today().isoformat(),)
        ).fetchone()[0]
        total_ce = conn.execute(
            "SELECT COUNT(*) FROM detections WHERE user_category='code_enforcement' OR (user_category IS NULL AND category='code_enforcement')"
        ).fetchone()[0]
        client.publish("code_enforcement/last_seen",   now,             retain=True)
        client.publish("code_enforcement/today_count", str(today_ce),   retain=True)
        client.publish("code_enforcement/total_count", str(total_ce),   retain=True)
        client.disconnect()
        return True
    except Exception as e:
        st.warning(f"MQTT publish failed: {e}")
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def thumbnail_data_uri(event_id: str) -> str:
    """Return a base64 data URI for the event thumbnail.
    Prefers the locally-saved copy (persists after Frigate prunes the event).
    Falls back to fetching from Frigate if the local file doesn't exist.
    Returns empty string if unavailable (Streamlit ImageColumn shows blank).
    """
    if not event_id:
        return ""
    local_path = os.path.join(THUMB_DIR, f"{event_id}.jpg")
    if os.path.exists(local_path):
        with open(local_path, "rb") as f:
            data = f.read()
    else:
        try:
            resp = requests.get(
                f"{FRIGATE_URL}/api/events/{event_id}/thumbnail.jpg", timeout=5
            )
            if resp.status_code != 200:
                return ""
            data = resp.content
            # Cache it locally for next time
            os.makedirs(THUMB_DIR, exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(data)
        except Exception:
            return ""
    return "data:image/jpeg;base64," + base64.b64encode(data).decode()


def effective_category(row) -> str:
    return row["user_category"] if row["user_category"] else (row["category"] or "unclassified")


# ── App ───────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Vehicle Log", layout="wide", page_icon="🚗")
st.title("🚗 Vehicle Detection Log")

conn = get_conn()

# ── Sidebar filters ───────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Filters")

    today = date.today()
    start_date = st.date_input("From", value=today - timedelta(days=30))
    end_date   = st.date_input("To",   value=today)

    cat_options = ["All (excl. known)", "All", "Unclassified only", "Needs review"] + [c for c in CATEGORIES if c]
    cat_filter = st.selectbox("Category", cat_options)

    reviewed_filter = st.selectbox("Review status", ["All", "Not reviewed", "Reviewed"])

    st.divider()
    st.caption(f"DB: `{DB_PATH}`")
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()
    empty_count = conn.execute(
        "SELECT COUNT(*) FROM detections WHERE (all_ocr_text IS NULL OR all_ocr_text = '') AND (user_category IS NULL OR user_category = '')"
    ).fetchone()[0]
    if empty_count:
        if st.button(f"🧹 Remove {empty_count} empty records"):
            conn.execute(
                "DELETE FROM detections WHERE (all_ocr_text IS NULL OR all_ocr_text = '') AND (user_category IS NULL OR user_category = '')"
            )
            conn.commit()
            st.rerun()

# ── Tabs ─────────────────────────────────────────────────────────────────────

tab_vehicles, tab_suggestions = st.tabs(["🚗 Vehicles", "🤖 Claude Suggestions"])

with tab_vehicles:

    # ── Metrics ───────────────────────────────────────────────────────────────

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total detections", total_count(conn))
    m2.metric("Today",            today_count(conn))
    m3.metric("Unclassified",     unclassified_count(conn))
    m4.metric("Code Enforcement", ce_count(conn))

    st.divider()

    # ── Load data ─────────────────────────────────────────────────────────────

    df = load_detections(conn, start_date, end_date, cat_filter, reviewed_filter)

    if df.empty:
        st.info("No detections match the current filters.")
        st.stop()

    # Build display DataFrame
    display = df.copy()
    display["snapshot"] = display["event_id"].apply(thumbnail_data_uri)
    display["effective"] = display.apply(effective_category, axis=1)
    display["timestamp"] = pd.to_datetime(display["timestamp"], utc=True)
    display["all_ocr_text"] = display["all_ocr_text"].fillna("").str[:120]
    display["car_confidence"] = display["car_confidence"].fillna(0.0)
    display["user_category"] = display["user_category"].fillna("")
    display["_select"] = False

    # Columns to show in editor
    editor_cols = ["_select", "id", "snapshot", "timestamp", "effective", "category",
                   "user_category", "car_confidence", "matched_text", "all_ocr_text", "reviewed"]
    original_user_cats = display["user_category"].copy()

    # ── Detection table ───────────────────────────────────────────────────────

    st.subheader(f"Detections ({len(df)})")

    edited = st.data_editor(
        display[editor_cols],
        column_config={
            "_select":         st.column_config.CheckboxColumn("☑",        width="small"),
            "id":              st.column_config.NumberColumn("ID",         width="small"),
            "snapshot":        st.column_config.ImageColumn("Snapshot",    width="medium"),
            "timestamp":       st.column_config.DatetimeColumn("Time",     format="MM/DD HH:mm", width="medium"),
            "effective":       st.column_config.TextColumn("Label",        width="small",  disabled=True),
            "category":        st.column_config.TextColumn("ML Pred",      width="small",  disabled=True),
            "user_category":   st.column_config.SelectboxColumn(
                                   "✏️ Correction",
                                   options=CATEGORIES,
                                   width="medium",
                               ),
            "car_confidence":  st.column_config.NumberColumn("Conf",       width="small",  format="%.2f", disabled=True),
            "matched_text":    st.column_config.TextColumn("Matched",      width="small",  disabled=True),
            "all_ocr_text":    st.column_config.TextColumn("Raw OCR",      width="large",  disabled=True),
            "reviewed":        st.column_config.CheckboxColumn("✓ Reviewed", width="small", disabled=True),
        },
        disabled=["id", "snapshot", "timestamp", "effective", "category",
                  "car_confidence", "matched_text", "all_ocr_text", "reviewed"],
        hide_index=True,
        use_container_width=True,
        height=500,
    )

    # ── Bulk assign ───────────────────────────────────────────────────────────

    selected_ids = edited[edited["_select"] == True].index.tolist()
    n_selected = len(selected_ids)

    bulk_col1, bulk_col2, bulk_col3, bulk_col4 = st.columns([2, 2, 1, 2])
    with bulk_col1:
        bulk_cat = st.selectbox(
            "Bulk assign selected to:",
            [c for c in CATEGORIES if c],
            key="bulk_cat",
            label_visibility="collapsed",
        )
    with bulk_col2:
        bulk_label = f"Apply to {n_selected} selected" if n_selected else "Apply to selected"
        bulk_clicked = st.button(bulk_label, disabled=(n_selected == 0))
    with bulk_col3:
        delete_clicked = st.button(f"🗑️ Delete", disabled=(n_selected == 0), type="secondary")
    with bulk_col4:
        if n_selected:
            st.caption(f"{n_selected} row(s) checked")
        else:
            st.caption("Check rows with ☑ to bulk-assign or delete")

    if delete_clicked and n_selected:
        ids_to_delete = [int(display.loc[idx, "id"]) for idx in selected_ids]
        conn.execute(f"DELETE FROM detections WHERE id IN ({','.join('?' * len(ids_to_delete))})", ids_to_delete)
        conn.commit()
        st.success(f"🗑️ Deleted {len(ids_to_delete)} record(s).")
        st.rerun()

    if bulk_clicked and n_selected:
        ce_alerted_bulk = []
        hashed_bulk = []
        for idx in selected_ids:
            row = display.loc[idx]
            conn.execute(
                "UPDATE detections SET user_category = ?, reviewed = 1 WHERE id = ?",
                (bulk_cat, int(row["id"]))
            )
            if bulk_cat == "code_enforcement":
                if republish_ce_alert(row):
                    ce_alerted_bulk.append(row["event_id"])
            if bulk_cat == "my_vehicle":
                if save_known_vehicle(conn, row["event_id"]):
                    hashed_bulk.append(row["event_id"])
        conn.commit()
        msg = f"✅ Applied **{bulk_cat}** to {n_selected} detection(s)."
        if hashed_bulk:
            msg += f" 🚗 Saved {len(hashed_bulk)} fingerprint(s)."
        if ce_alerted_bulk:
            msg += f" 🚨 Fired {len(ce_alerted_bulk)} CE alert(s)."
        st.success(msg)
        st.rerun()

    st.divider()

    # ── Save corrections ──────────────────────────────────────────────────────

    save_col, info_col = st.columns([1, 4])
    with save_col:
        save_clicked = st.button("💾 Save corrections", type="primary")

    changed_mask = edited["user_category"] != original_user_cats
    n_changed = changed_mask.sum()

    with info_col:
        if n_changed > 0:
            st.info(f"{n_changed} row(s) modified — click Save to write to DB")
        else:
            st.caption("Edit the ✏️ Correction column to reclassify a detection")

    if save_clicked:
        if n_changed == 0:
            st.warning("No changes to save.")
        else:
            ce_alerted = []
            hashed = []
            for idx in edited[changed_mask].index:
                row     = display.loc[idx]
                new_cat = edited.loc[idx, "user_category"] or None
                conn.execute(
                    "UPDATE detections SET user_category = ?, reviewed = 1 WHERE id = ?",
                    (new_cat, int(row["id"]))
                )
                if new_cat == "code_enforcement":
                    if republish_ce_alert(row):
                        ce_alerted.append(row.get("event_id", "?"))
                if new_cat == "my_vehicle":
                    if save_known_vehicle(conn, row["event_id"]):
                        hashed.append(row["event_id"])
            conn.commit()

            msg = f"✅ Saved {n_changed} correction(s)."
            if hashed:
                msg += f" 🚗 Added {len(hashed)} vehicle fingerprint(s) — future matches auto-classified."
            if ce_alerted:
                msg += f" 🚨 Code Enforcement alert fired for {len(ce_alerted)} event(s)."
            st.success(msg)
            st.rerun()

    # ── Stats charts ──────────────────────────────────────────────────────────

    st.divider()
    st.subheader("Stats")

    chart_df = df.copy()
    chart_df["label"] = chart_df.apply(effective_category, axis=1)
    chart_df["date_str"] = chart_df["date"].astype(str)

    col_bar, col_pie = st.columns(2)

    with col_bar:
        daily = (
            chart_df.groupby(["date_str", "label"])
            .size()
            .reset_index(name="count")
            .sort_values("date_str")
        )
        if not daily.empty:
            fig = px.bar(
                daily,
                x="date_str", y="count", color="label",
                color_discrete_map=CATEGORY_COLORS,
                labels={"date_str": "Date", "count": "Detections", "label": "Category"},
                title="Detections per day",
            )
            fig.update_layout(xaxis_tickangle=-45, legend_title="Category")
            st.plotly_chart(fig, use_container_width=True)

    with col_pie:
        breakdown = chart_df["label"].value_counts().reset_index()
        breakdown.columns = ["category", "count"]
        if not breakdown.empty:
            fig2 = px.pie(
                breakdown,
                values="count", names="category",
                color="category",
                color_discrete_map=CATEGORY_COLORS,
                title="Category breakdown",
            )
            st.plotly_chart(fig2, use_container_width=True)

    # ── Known Vehicles ────────────────────────────────────────────────────────

    st.divider()
    with st.expander(f"🚗 Known Vehicles (fingerprint library)", expanded=False):
        kv_df = load_known_vehicles(conn)

        if kv_df.empty:
            st.info(
                "No vehicle fingerprints stored yet. "
                "Tag a detection as **my_vehicle** and save to add one."
            )
        else:
            st.caption(
                f"{len(kv_df)} fingerprint(s) stored. "
                "The detection service checks every new car against these before running OCR."
            )

            for _, kv_row in kv_df.iterrows():
                c_img, c_meta, c_del = st.columns([1, 3, 1])
                with c_img:
                    thumb = thumbnail_data_uri(kv_row["event_id"])
                    if thumb:
                        st.image(thumb, width=120)
                with c_meta:
                    st.markdown(f"**Event:** `{kv_row['event_id']}`")
                    st.markdown(f"**Added:** {kv_row['created_at'][:19]}")
                with c_del:
                    if st.button("🗑️ Remove", key=f"del_kv_{kv_row['id']}"):
                        conn.execute("DELETE FROM known_vehicles WHERE id = ?", (int(kv_row["id"]),))
                        conn.commit()
                        st.rerun()

        st.caption(
            "**How it works:** each thumbnail is hashed into a 64-bit perceptual fingerprint. "
            "On each new car detection, the service computes the same hash and compares "
            "against all stored fingerprints. If the Hamming distance is ≤ 12 bits (configurable "
            "via `PHASH_THRESHOLD` env var), the car is auto-classified as `my_vehicle` and OCR "
            "is skipped entirely. Tag multiple detections of each vehicle from different angles "
            "and lighting conditions to improve recall."
        )

with tab_suggestions:
    st.caption(
        "Claude reviews pending detections on request and writes a suggested category + confidence "
        "here. Nothing is applied automatically — review the snapshot, then approve individually or "
        "in bulk. This replaces classifying every detection from scratch."
    )

    sugg_df = load_claude_suggestions(conn)
    notes_df = load_claude_notes_only(conn)

    if sugg_df.empty and notes_df.empty:
        st.success("No pending Claude-reviewed items right now.")
    else:
        if not sugg_df.empty:
            st.subheader(f"Suggested categories awaiting approval ({len(sugg_df)})")

            sugg_display = sugg_df.copy()
            sugg_display["snapshot"] = sugg_display["event_id"].apply(thumbnail_data_uri)
            sugg_display["timestamp"] = pd.to_datetime(sugg_display["timestamp"], utc=True)
            sugg_display["_select"] = True  # default-checked: this is the "mass approve" surface

            sugg_cols = ["_select", "id", "snapshot", "timestamp", "claude_suggestion",
                         "claude_confidence", "claude_notes"]

            sugg_edited = st.data_editor(
                sugg_display[sugg_cols],
                column_config={
                    "_select":           st.column_config.CheckboxColumn("☑ Approve", width="small"),
                    "id":                st.column_config.NumberColumn("ID", width="small"),
                    "snapshot":          st.column_config.ImageColumn("Snapshot", width="medium"),
                    "timestamp":         st.column_config.DatetimeColumn("Time", format="MM/DD HH:mm", width="medium"),
                    "claude_suggestion": st.column_config.TextColumn("Claude's Suggestion", width="small"),
                    "claude_confidence": st.column_config.ProgressColumn(
                                             "Confidence", min_value=0, max_value=1, format="%.2f", width="small"),
                    "claude_notes":      st.column_config.TextColumn("Why", width="large", disabled=True),
                },
                disabled=["id", "snapshot", "timestamp", "claude_suggestion", "claude_confidence", "claude_notes"],
                hide_index=True,
                use_container_width=True,
                height=400,
            )

            approve_selected = sugg_edited[sugg_edited["_select"] == True].index.tolist()
            n_approve = len(approve_selected)

            ac1, ac2 = st.columns([1, 4])
            with ac1:
                approve_clicked = st.button(
                    f"✅ Approve {n_approve} selected" if n_approve else "✅ Approve selected",
                    disabled=(n_approve == 0),
                    type="primary",
                )
            with ac2:
                st.caption("Checked rows default to approved — uncheck any you want to skip or correct manually in the Vehicles tab instead.")

            if approve_clicked and n_approve:
                ce_alerted = []
                hashed = []
                for idx in approve_selected:
                    row = sugg_display.loc[idx]
                    new_cat = row["claude_suggestion"]
                    conn.execute(
                        "UPDATE detections SET user_category = ?, reviewed = 1 WHERE id = ?",
                        (new_cat, int(row["id"]))
                    )
                    if new_cat == "code_enforcement":
                        if republish_ce_alert(row):
                            ce_alerted.append(row["event_id"])
                    if new_cat == "my_vehicle":
                        if save_known_vehicle(conn, row["event_id"]):
                            hashed.append(row["event_id"])
                conn.commit()
                msg = f"✅ Approved {n_approve} Claude suggestion(s)."
                if hashed:
                    msg += f" 🚗 Saved {len(hashed)} fingerprint(s)."
                if ce_alerted:
                    msg += f" 🚨 Fired {len(ce_alerted)} CE alert(s)."
                st.success(msg)
                st.rerun()

        if not notes_df.empty:
            st.divider()
            st.subheader(f"Needs your judgment, no auto-suggestion ({len(notes_df)})")
            st.caption(
                "Claude looked at these but wasn't confident enough to propose a category — "
                "e.g. a recurring vehicle not yet in the fingerprint library, or an event whose "
                "image was already purged by Frigate before review. Classify directly here — "
                "same correction/bulk-assign as the Vehicles tab, no need to switch tabs."
            )

            notes_display = notes_df.copy()
            notes_display["snapshot"] = notes_display["event_id"].apply(thumbnail_data_uri)
            notes_display["timestamp"] = pd.to_datetime(notes_display["timestamp"], utc=True)
            notes_display["_select"] = False
            notes_display["user_category"] = ""

            notes_editor_cols = ["_select", "id", "snapshot", "timestamp", "claude_notes", "user_category"]

            notes_edited = st.data_editor(
                notes_display[notes_editor_cols],
                column_config={
                    "_select":       st.column_config.CheckboxColumn("☑", width="small"),
                    "id":            st.column_config.NumberColumn("ID", width="small"),
                    "snapshot":      st.column_config.ImageColumn("Snapshot", width="medium"),
                    "timestamp":     st.column_config.DatetimeColumn("Time", format="MM/DD HH:mm", width="medium"),
                    "claude_notes":  st.column_config.TextColumn("Claude's Notes", width="large", disabled=True),
                    "user_category": st.column_config.SelectboxColumn(
                                          "✏️ Correction", options=CATEGORIES, width="medium"),
                },
                disabled=["id", "snapshot", "timestamp", "claude_notes"],
                hide_index=True,
                use_container_width=True,
                height=400,
                key="notes_editor",
            )

            notes_selected = notes_edited[notes_edited["_select"] == True].index.tolist()
            n_notes_selected = len(notes_selected)

            nc1, nc2, nc3 = st.columns([2, 2, 3])
            with nc1:
                notes_bulk_cat = st.selectbox(
                    "Bulk assign selected to:", [c for c in CATEGORIES if c],
                    key="notes_bulk_cat", label_visibility="collapsed",
                )
            with nc2:
                notes_bulk_clicked = st.button(
                    f"Apply to {n_notes_selected} selected" if n_notes_selected else "Apply to selected",
                    disabled=(n_notes_selected == 0), key="notes_bulk_apply",
                )
            with nc3:
                st.caption(f"{n_notes_selected} row(s) checked" if n_notes_selected
                           else "Check rows to bulk-assign, or edit ✏️ Correction per-row and save below")

            def _apply_category(conn, row_id, category, event_id):
                conn.execute(
                    "UPDATE detections SET user_category = ?, reviewed = 1 WHERE id = ?",
                    (category, int(row_id))
                )
                ce_fired = my_vehicle_hashed = False
                if category == "code_enforcement":
                    ce_fired = republish_ce_alert({"event_id": event_id, "snapshot_url": ""})
                if category == "my_vehicle":
                    my_vehicle_hashed = save_known_vehicle(conn, event_id)
                return ce_fired, my_vehicle_hashed

            if notes_bulk_clicked and n_notes_selected:
                ce_count_, hash_count_ = 0, 0
                for idx in notes_selected:
                    row = notes_display.loc[idx]
                    ce_fired, hashed = _apply_category(conn, row["id"], notes_bulk_cat, row["event_id"])
                    ce_count_ += int(ce_fired)
                    hash_count_ += int(hashed)
                conn.commit()
                msg = f"✅ Applied **{notes_bulk_cat}** to {n_notes_selected} detection(s)."
                if hash_count_:
                    msg += f" 🚗 Saved {hash_count_} fingerprint(s)."
                if ce_count_:
                    msg += f" 🚨 Fired {ce_count_} CE alert(s)."
                st.success(msg)
                st.rerun()

            notes_changed = notes_edited[notes_edited["user_category"] != ""]
            if st.button("💾 Save individual corrections", key="notes_save", disabled=notes_changed.empty):
                ce_count_, hash_count_ = 0, 0
                for idx in notes_changed.index:
                    row = notes_display.loc[idx]
                    new_cat = notes_edited.loc[idx, "user_category"]
                    ce_fired, hashed = _apply_category(conn, row["id"], new_cat, row["event_id"])
                    ce_count_ += int(ce_fired)
                    hash_count_ += int(hashed)
                conn.commit()
                msg = f"✅ Saved {len(notes_changed)} correction(s)."
                if hash_count_:
                    msg += f" 🚗 Saved {hash_count_} fingerprint(s)."
                if ce_count_:
                    msg += f" 🚨 Fired {ce_count_} CE alert(s)."
                st.success(msg)
                st.rerun()
