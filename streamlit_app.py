from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from snapims import __version__, active_batch, db
from snapims.config import DataPaths, ShopifyConfig
from snapims.inventory import (
    export_audit_csv,
    export_inventory_csv,
    import_inventory_csv,
    validate_items,
)
from snapims.pipeline import parse_batch
from snapims.processor import process_batch
from snapims.recognition.progress import latest_job
from snapims.recognition.review_ui import render_batch_details_section, render_review
from snapims.shopify.publish import (
    build_publish_queue,
    create_selected_drafts,
    simulate_selected,
)
from snapims.shopify.service import ShopifyService

load_dotenv()
st.set_page_config(page_title="SnapIMS", page_icon="📸", layout="wide")
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.5rem; max-width: 1450px;}
      [data-testid="stMetric"] {background:#f5f7fa;border:1px solid #e1e6ed;padding:14px;border-radius:12px;}
      .snap-card {border:1px solid #dbe2ea;border-radius:12px;padding:12px;background:white;margin-bottom:12px;}
      .small-muted {color:#687387;font-size:.88rem;}
      .shortcut-strip {position:sticky;top:2.6rem;z-index:50;background:#17213a;color:white;
        border-radius:8px;padding:7px 10px;margin:-6px 0 8px;font-size:.78rem;
        display:flex;gap:12px;align-items:center;white-space:nowrap;overflow-x:auto;}
      .shortcut-strip b {color:#9ee7d8;margin-right:-7px;}
      .review-cover img {max-height:50vh;object-fit:contain;background:#111827;border-radius:8px;}
      .review-heading {display:flex;align-items:center;gap:7px;margin-bottom:5px;}
      .queue-position {margin-left:auto;font-weight:700;color:#475569;}
      .status-badge {display:inline-block;border-radius:999px;padding:3px 9px;font-size:.72rem;
        font-weight:800;text-transform:uppercase;letter-spacing:.04em;background:#e2e8f0;color:#334155;}
      .status-badge.done {background:#dcfce7;color:#166534;}
      .status-badge.failed {background:#fee2e2;color:#991b1b;}
      .status-badge.needs-attention {background:#ffedd5;color:#9a3412;}
      .status-badge.to-review {background:#dbeafe;color:#1e40af;}
      .item-context {font-size:.77rem;color:#64748b;border-bottom:1px solid #e2e8f0;
        padding-bottom:7px;margin-bottom:8px;}
      .suggestion-title {font-size:1.55rem;font-weight:800;line-height:1.1;margin:4px 0 10px;}
      .metadata-grid {display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:7px;}
      .metadata-grid div {background:#f8fafc;border:1px solid #e2e8f0;border-radius:7px;padding:6px 8px;}
      .metadata-grid .wide {grid-column:1 / -1;}
      .metadata-grid span {display:block;color:#64748b;font-size:.68rem;text-transform:uppercase;}
      .metadata-grid b {display:block;font-size:.87rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
      @media (max-width: 760px) {.shortcut-strip {position:static}.review-cover img {max-height:42vh;}}
    </style>
    """,
    unsafe_allow_html=True,
)


def data_paths() -> DataPaths:
    root = st.session_state.get("data_root") or os.getenv("SNAPIMS_DATA_DIR") or "~/SnapIMS-data"
    paths = DataPaths.from_root(root).ensure()
    db.initialize(paths.db_file)
    return paths


def active_batch_default_index(db_file: Path, batch_options: list[str]) -> int:
    """Return the index of the durable active batch within ``batch_options``.

    Falls back to 0 (the most recent batch) when no active batch is set or
    the stored one is no longer present, without persisting a change.
    """
    active = active_batch.get_active_batch(db_file)
    if active and active["batch_id"] in batch_options:
        return batch_options.index(active["batch_id"])
    return 0


paths = data_paths()
with st.sidebar:
    st.title("📸 SnapIMS")
    st.caption(f"Prototype {__version__}")
    workspace_pages = ["Home", "Import", "Review", "Publish", "Settings & diagnostics"]
    pending_page = st.session_state.pop("pending_workspace_page", None)
    if pending_page in workspace_pages:
        st.session_state["workspace_page"] = pending_page
    page = st.radio(
        "Workspace",
        workspace_pages,
        key="workspace_page",
    )


if page == "Home":
    st.title("SnapIMS home")
    st.caption("Encode intent into inevitable actions. The photography stream is the inventory event log.")
    summary = db.database_summary(paths.db_file)
    columns = st.columns(5)
    for column, label, value in zip(
        columns, ("Batches", "Items", "Ready", "Uploaded", "Blocked"), summary.values(), strict=True
    ):
        column.metric(label, value)

    st.subheader("Active batch")
    batches = db.list_batches(paths.db_file)
    if not batches:
        st.info("No batches yet. Open Import to process the demo or a Pixel session.")
    else:
        batch_options = [row["batch_id"] for row in batches]
        active = active_batch.get_active_batch(paths.db_file)
        if active is None:
            st.warning("No active batch is set. Choose one below.")
            default_index = 0
        else:
            next_action = active_batch.compute_next_action(paths.db_file, active["batch_id"])
            info_col, action_col = st.columns([3, 1])
            with info_col:
                st.markdown(f"**{active['batch_id']}**")
                st.caption(f"Imported {active['imported_at']} · {active['item_count']} item(s)")
                st.info(f"**Next:** {next_action.label}. {next_action.detail}")
                recognition_job = latest_job(paths.db_file, active["batch_id"])
                if recognition_job is not None:
                    st.caption(
                        f"Recognition resume: {recognition_job.completed}/{recognition_job.total} "
                        f"completed · {recognition_job.remaining} remaining · "
                        f"{recognition_job.failed} failed"
                    )
            with action_col:
                if st.button(
                    "Continue", type="primary", key="dashboard_continue", width="stretch"
                ):
                    st.session_state["pending_workspace_page"] = next_action.target_page
                    st.rerun()
            default_index = (
                batch_options.index(active["batch_id"])
                if active["batch_id"] in batch_options
                else 0
            )
        with st.expander("Change batch", expanded=active is None):
            chosen = st.selectbox(
                "Batch", batch_options, index=default_index, key="dashboard_change_batch"
            )
            if st.button("Set as active batch", key="dashboard_set_active"):
                active_batch.set_active_batch(paths.db_file, chosen)
                st.rerun()

    st.subheader("Recent batches")
    if batches:
        st.dataframe(
            [
                {
                    "Batch": row["batch_id"], "Imported": row["imported_at"],
                    "Items": row["item_count"], "Images": row["product_photo_count"],
                    "Commands": row["command_count"], "Warnings": row["warning_count"],
                }
                for row in batches
            ],
            hide_index=True,
            width="stretch",
        )

elif page == "Import":
    st.title("Import a QR-delimited photo batch")
    st.info("Time restores order only. CVHS1:ITEM:NEXT is the sole normal item boundary.")
    source_text = st.text_input("Photo directory", placeholder="/home/isaiah/Pictures/SnapIMS/session-001")
    batch_name = st.text_input("Optional batch name", placeholder="COMEDY")
    recursive = st.checkbox("Include subfolders", value=False)
    preview_col, import_col = st.columns(2)
    if preview_col.button("Dry-run parser preview", type="primary", width="stretch"):
        try:
            preview = parse_batch(Path(source_text), batch_name=batch_name or None, recursive=recursive)
            st.session_state["preview"] = preview
        except Exception as exc:
            st.error(str(exc))
    if import_col.button("Preserve and import batch", width="stretch"):
        try:
            result = process_batch(
                Path(source_text), paths=paths, batch_name=batch_name or None, recursive=recursive
            )
            st.success(
                f"{'Already imported' if result.duplicate else 'Imported'} {result.batch_id}: "
                f"{result.item_count} items, {result.product_photo_count} product images."
            )
            st.code(str(result.output_folder))
            if result.warnings:
                st.warning("\n".join(result.warnings))
            st.session_state["last_imported_batch"] = result.batch_id
        except Exception as exc:
            st.exception(exc)
    preview = st.session_state.get("preview")
    if preview:
        st.subheader(f"Preview · {preview.batch_id}")
        a, b, c, d = st.columns(4)
        a.metric("Items", len(preview.items))
        b.metric("Product images", preview.photo_count)
        c.metric("Commands", len(preview.commands))
        d.metric("Warnings", len(preview.warnings))
        st.dataframe(
            [
                {
                    "Sequence": item.sequence, "Shelf": item.shelf,
                    "Images": len(item.photos), "Rare": item.rare, "Review": item.review,
                    "Front": item.front.original_name,
                }
                for item in preview.items
            ],
            hide_index=True, width="stretch",
        )
        with st.expander("Command stream (technical evidence)", expanded=False):
            st.dataframe(
                [
                    {
                        "#": command.stream_index, "Time": command.captured_at,
                        "Payload": command.qr_payload, "Photo": command.original_name,
                    }
                    for command in preview.commands
                ], hide_index=True, width="stretch",
            )
        if preview.warnings:
            st.warning("\n".join(preview.warnings))

    last_imported = st.session_state.get("last_imported_batch")
    if last_imported and db.batch_exists(paths.db_file, last_imported):
        if st.button("Continue to Review", type="primary", key="import_continue_to_review"):
            st.session_state["pending_workspace_page"] = "Review"
            st.rerun()

    st.divider()
    st.subheader("Batch details")
    st.caption(
        "Human-readable item grouping for any imported batch. Raw command-stream "
        "fields remain reachable under Settings & diagnostics."
    )
    batches = db.list_batches(paths.db_file)
    if not batches:
        st.info("No batches yet.")
    else:
        batch_options = [row["batch_id"] for row in batches]
        selected_batch = st.selectbox(
            "Batch",
            batch_options,
            index=active_batch_default_index(paths.db_file, batch_options),
            key="import_batch_details_batch",
        )
        render_batch_details_section(paths.db_file, selected_batch)

elif page == "Review":
    render_review(paths)

elif page == "Publish":
    st.title("Publish")
    st.warning(
        "Simulation is the default. SnapIMS never publishes products; live mode creates DRAFTS only."
    )
    config = ShopifyConfig.from_env()
    service = ShopifyService(paths.db_file, config)
    batches = db.list_batches(paths.db_file)
    if not batches:
        st.info("Import a batch first.")
        batch_id_value = ""
        queue = []
    else:
        batch_options = [row["batch_id"] for row in batches]
        batch_id_value = st.selectbox(
            "Batch",
            batch_options,
            index=active_batch_default_index(paths.db_file, batch_options),
            key="publish_batch",
        )
        queue = build_publish_queue(paths.db_file, batch_id_value)
    if queue:
        counts = {
            state: sum(entry.state == state for entry in queue)
            for state in ("Ready", "Blocked", "Drafted", "Failed")
        }
        for column, state in zip(st.columns(4), counts, strict=True):
            column.metric(state, counts[state])
        state_filter = st.segmented_control(
            "Queue", ["Ready", "Blocked", "Drafted", "Failed"], default="Ready"
        )
        visible = [entry for entry in queue if entry.state == state_filter]
        for entry in visible:
            label = f"#{entry.sequence} · {entry.title}"
            if entry.reasons:
                label += " — " + "; ".join(entry.reasons)
            st.write(label)
            if entry.admin_url:
                st.link_button("Open in Shopify", entry.admin_url)

        selectable = [entry for entry in queue if entry.state in {"Ready", "Failed"}]
        selected_ids = st.multiselect(
            "Items selected for draft preparation",
            [entry.item_id for entry in selectable],
            default=[entry.item_id for entry in selectable],
            format_func=lambda value: next(
                entry.title for entry in selectable if entry.item_id == value
            ),
            key="publish_selected_items",
        )
        remote_check = st.checkbox("Check selected SKUs in Shopify (read-only)", value=False)
        if st.button("Simulate selected drafts", type="primary"):
            reports = simulate_selected(service, selected_ids, remote_check=remote_check)
            for report in reports:
                if report.ready:
                    st.success(f"{report.item_id}: ready to create a draft")
                else:
                    st.error(f"{report.item_id}: {'; '.join(report.errors)}")
        with st.expander("Deliberate live DRAFT creation"):
            phrase = st.text_input("Type CREATE SELECTED DRAFTS to enable the write button")
            understand = st.checkbox(
                "I confirm only the selected items will be written as Shopify drafts"
            )
            enabled = bool(selected_ids) and understand and phrase == "CREATE SELECTED DRAFTS"
            if st.button("Create selected Shopify DRAFTS", disabled=not enabled):
                outcomes = create_selected_drafts(service, selected_ids, confirmed=True)
                for outcome in outcomes:
                    if outcome.outcome == "DRAFTED":
                        st.success(f"{outcome.item_id}: draft created")
                    elif outcome.outcome == "SKIPPED_DRAFTED":
                        st.info(f"{outcome.item_id}: existing draft retained")
                    else:
                        st.error(f"{outcome.item_id}: {outcome.message}")
                st.rerun()
    elif batches:
        st.info("No items in this batch.")

    st.divider()
    st.subheader("CSV tools")
    if not batches:
        st.info("Import a batch first.")
    else:
        destination = paths.processed / batch_id_value / "inventory_work.csv"
        export_inventory_csv(paths.db_file, batch_id_value, destination)
        st.download_button(
            "Download current inventory_work.csv",
            destination.read_bytes(),
            file_name=f"{batch_id_value}-inventory_work.csv",
            mime="text/csv",
        )
        uploaded = st.file_uploader("Import edited inventory_work.csv", type="csv")
        if uploaded and st.button("Validate and import CSV", type="primary"):
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as temp:
                temp.write(uploaded.getvalue())
                temp_path = Path(temp.name)
            try:
                count = import_inventory_csv(
                    paths.db_file,
                    temp_path,
                    paths=paths,
                    expected_batch_id=batch_id_value,
                )
                export_inventory_csv(paths.db_file, batch_id_value, destination)
                st.success(f"Updated {count} row(s) by Item ID. Row order was ignored.")
            except Exception as exc:
                st.error(str(exc))
            finally:
                temp_path.unlink(missing_ok=True)

elif page == "Settings & diagnostics":
    st.title("Settings & diagnostics")
    with st.expander("Workspace storage", expanded=False):
        configured_root = st.text_input("Data directory", value=str(paths.root))
        if configured_root != str(paths.root) and st.button("Use data directory"):
            st.session_state["data_root"] = configured_root
            st.rerun()
        st.caption(f"Database path: {paths.db_file}")

    with st.expander("Database inspection and audit", expanded=False):
        with db.connect(paths.db_file) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        st.metric("SQLite integrity", integrity)
        tables = [
            "schema_migrations", "batches", "items", "photos", "command_events",
            "recognition_results", "catalog_products", "inventory_events", "shopify_sync",
            "settings", "upload_attempts",
        ]
        table = st.selectbox("Table", tables)
        with db.connect(paths.db_file) as connection:
            rows = connection.execute(f"SELECT * FROM {table} LIMIT 1000").fetchall()
        st.dataframe([dict(row) for row in rows], hide_index=True, width="stretch")
        audit_path = paths.exports / f"inventory-events-{os.getpid()}.csv"
        if st.button("Generate inventory event audit CSV"):
            export_audit_csv(paths.db_file, audit_path)
        if audit_path.exists():
            st.download_button(
                "Download audit CSV",
                audit_path.read_bytes(),
                file_name="inventory-events.csv",
            )

    with st.expander("Command events (raw)", expanded=False):
        batches = db.list_batches(paths.db_file)
        if not batches:
            st.info("Import a batch first.")
        else:
            batch_options = [row["batch_id"] for row in batches]
            selected = st.selectbox(
                "Batch",
                batch_options,
                index=active_batch_default_index(paths.db_file, batch_options),
                key="diagnostics_command_events_batch",
            )
            with db.connect(paths.db_file) as connection:
                events = connection.execute(
                    """
                    SELECT e.stream_index, e.occurred_at, e.payload, e.command_kind,
                           e.command_value, p.original_name, p.original_copy_path
                    FROM command_events e JOIN photos p ON p.photo_id=e.source_photo_id
                    WHERE e.batch_id=? ORDER BY e.stream_index
                    """, (selected,),
                ).fetchall()
            st.dataframe([dict(row) for row in events], hide_index=True, width="stretch")
            if events:
                event_index = st.selectbox(
                    "Inspect command image",
                    [row["stream_index"] for row in events],
                    key="diagnostics_command_events_image",
                )
                event = next(row for row in events if row["stream_index"] == event_index)
                st.image(event["original_copy_path"], caption=event["payload"], width=520)

    with st.expander("Validation (raw)", expanded=False):
        batches = db.list_batches(paths.db_file)
        batch_options = [""] + [row["batch_id"] for row in batches]
        active = active_batch.get_active_batch(paths.db_file)
        default_index = (
            batch_options.index(active["batch_id"])
            if active and active["batch_id"] in batch_options
            else 0
        )
        selected = st.selectbox(
            "Batch", batch_options, index=default_index, key="diagnostics_validation_batch"
        )
        if st.button("Validate selected batch", type="primary", key="diagnostics_validate_button"):
            item_ids = [
                item["item_id"]
                for item in db.list_items(paths.db_file, batch_id_value=selected or None)
            ]
            results = validate_items(paths.db_file, item_ids)
            st.success(f"Validated {len(results)} item(s).")
        items = db.list_items(paths.db_file, batch_id_value=selected or None)
        st.dataframe(
            [
                {
                    "Item ID": item["item_id"], "Title": item["title"],
                    "Ready": bool(item["ready"]), "Status": item["validation_status"],
                    "Errors": "; ".join(json.loads(item["validation_errors"])),
                }
                for item in items
            ], hide_index=True, width="stretch",
        )

    with st.expander("Logs & warnings", expanded=False):
        batches = db.list_batches(paths.db_file)
        if not batches:
            st.info("No batches yet.")
        else:
            batch_options = [row["batch_id"] for row in batches]
            selected = st.selectbox(
                "Batch",
                batch_options,
                index=active_batch_default_index(paths.db_file, batch_options),
                key="diagnostics_logs_batch",
            )
            batch = next(row for row in batches if row["batch_id"] == selected)
            warnings = json.loads(batch["warnings_json"])
            if warnings:
                for warning in warnings:
                    st.warning(warning)
            else:
                st.success("No parser warnings for this batch.")
        st.markdown("**Structured application log**")
        log_path = paths.logs / "snapims.log"
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
            st.code("\n".join(lines) or "Log is empty.")
        else:
            st.info("The log will appear after the first import.")
