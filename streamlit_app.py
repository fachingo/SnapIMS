from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from snapims import __version__, db
from snapims.config import DataPaths, ShopifyConfig
from snapims.inventory import (
    CONDITIONS,
    POOL_MODES,
    export_audit_csv,
    export_inventory_csv,
    import_inventory_csv,
    validate_items,
)
from snapims.pipeline import parse_batch
from snapims.processor import process_batch
from snapims.recognition.providers import recognizer_registry
from snapims.recognition.service import (
    BatchRecognitionProgress,
    accept_result,
    list_results,
    run_batch_recognition,
    run_recognition,
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
    </style>
    """,
    unsafe_allow_html=True,
)


def data_paths() -> DataPaths:
    root = st.session_state.get("data_root") or os.getenv("SNAPIMS_DATA_DIR") or "~/SnapIMS-data"
    paths = DataPaths.from_root(root).ensure()
    db.initialize(paths.db_file)
    return paths


def money(cents: int | None) -> float:
    return 0.0 if cents is None else cents / 100


def show_images(db_file: Path, item_id_value: str) -> None:
    photos = db.get_item_photos(db_file, item_id_value)
    if not photos:
        st.warning("No images are associated with this item.")
        return
    front, *optional = photos
    left, right = st.columns([1.35, 1])
    with left:
        st.image(front["processed_path"], caption=f"Front · {front['proposed_name']}", use_container_width=True)
    with right:
        if optional:
            columns = st.columns(2)
            for index, photo in enumerate(optional):
                with columns[index % 2]:
                    st.image(photo["thumbnail_path"], caption=photo["proposed_name"], use_container_width=True)
        else:
            st.info("This item has one photograph.")


paths = data_paths()
with st.sidebar:
    st.title("📸 SnapIMS")
    st.caption(f"Prototype {__version__}")
    configured_root = st.text_input("Data directory", value=str(paths.root))
    if configured_root != str(paths.root) and st.button("Use data directory"):
        st.session_state["data_root"] = configured_root
        st.rerun()
    page = st.radio(
        "Workspace",
        [
            "Dashboard", "Import batch", "Command events", "Item grid", "Item editor",
            "CSV workflow", "Validation", "Database", "Recognition", "Shopify dry-run",
            "Logs & warnings",
        ],
    )
    st.caption(f"Database: {paths.db_file}")


if page == "Dashboard":
    st.title("SnapIMS dashboard")
    st.caption("Encode intent into inevitable actions. The photography stream is the inventory event log.")
    summary = db.database_summary(paths.db_file)
    columns = st.columns(5)
    for column, label, value in zip(
        columns, ("Batches", "Items", "Ready", "Uploaded", "Blocked"), summary.values(), strict=True
    ):
        column.metric(label, value)
    st.subheader("Recent batches")
    batches = db.list_batches(paths.db_file)
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
            use_container_width=True,
        )
    else:
        st.info("No batches yet. Open Import batch to process the demo or a Pixel session.")

elif page == "Import batch":
    st.title("Import a QR-delimited photo batch")
    st.info("Time restores order only. CVHS1:ITEM:NEXT is the sole normal item boundary.")
    source_text = st.text_input("Photo directory", placeholder="/home/isaiah/Pictures/SnapIMS/session-001")
    batch_name = st.text_input("Optional batch name", placeholder="COMEDY")
    recursive = st.checkbox("Include subfolders", value=False)
    preview_col, import_col = st.columns(2)
    if preview_col.button("Dry-run parser preview", type="primary", use_container_width=True):
        try:
            preview = parse_batch(Path(source_text), batch_name=batch_name or None, recursive=recursive)
            st.session_state["preview"] = preview
        except Exception as exc:
            st.error(str(exc))
    if import_col.button("Preserve and import batch", use_container_width=True):
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
            hide_index=True, use_container_width=True,
        )
        with st.expander("Command stream", expanded=True):
            st.dataframe(
                [
                    {
                        "#": command.stream_index, "Time": command.captured_at,
                        "Payload": command.qr_payload, "Photo": command.original_name,
                    }
                    for command in preview.commands
                ], hide_index=True, use_container_width=True,
            )
        if preview.warnings:
            st.warning("\n".join(preview.warnings))

elif page == "Command events":
    st.title("Command-event review")
    batches = db.list_batches(paths.db_file)
    if not batches:
        st.info("Import a batch first.")
    else:
        selected = st.selectbox("Batch", [row["batch_id"] for row in batches])
        with db.connect(paths.db_file) as connection:
            events = connection.execute(
                """
                SELECT e.stream_index, e.occurred_at, e.payload, e.command_kind,
                       e.command_value, p.original_name, p.original_copy_path
                FROM command_events e JOIN photos p ON p.photo_id=e.source_photo_id
                WHERE e.batch_id=? ORDER BY e.stream_index
                """, (selected,),
            ).fetchall()
        st.dataframe([dict(row) for row in events], hide_index=True, use_container_width=True)
        event_index = st.selectbox("Inspect command image", [row["stream_index"] for row in events])
        event = next(row for row in events if row["stream_index"] == event_index)
        st.image(event["original_copy_path"], caption=event["payload"], width=520)

elif page == "Item grid":
    st.title("Item thumbnail grid")
    batches = db.list_batches(paths.db_file)
    selected_batch = st.selectbox("Batch", [""] + [row["batch_id"] for row in batches])
    items = db.list_items(paths.db_file, batch_id_value=selected_batch or None)
    if not items:
        st.info("No items match this view.")
    else:
        columns = st.columns(4)
        for index, item in enumerate(items):
            with columns[index % 4]:
                st.markdown('<div class="snap-card">', unsafe_allow_html=True)
                if item["front_thumbnail"]:
                    st.image(item["front_thumbnail"], use_container_width=True)
                st.markdown(f"**{item['title'] or 'Untitled VHS'}**")
                st.caption(
                    f"{item['item_id']} · Shelf {item['shelf']} · {item['image_count']} image(s)"
                )
                flags = [name for name, value in (("RARE", item["rare"]), ("REVIEW", item["review"])) if value]
                if flags:
                    st.warning(" · ".join(flags))
                st.markdown('</div>', unsafe_allow_html=True)

elif page == "Item editor":
    st.title("Item editor")
    items = db.list_items(paths.db_file)
    if not items:
        st.info("Import a batch first.")
    else:
        labels = {f"{item['item_id']} · {item['title'] or 'Untitled'}": item for item in items}
        selected_label = st.selectbox("Item", list(labels))
        item = labels[selected_label]
        show_images(paths.db_file, item["item_id"])
        with st.form("item-editor"):
            c1, c2, c3 = st.columns(3)
            title = c1.text_input("Title", value=item["title"])
            edition = c2.text_input("Edition", value=item["edition"])
            distributor = c3.text_input("Distributor", value=item["distributor"])
            c1, c2, c3, c4 = st.columns(4)
            price = c1.number_input("Price", min_value=0.0, value=money(item["price_cents"]), step=1.0)
            quantity = c2.number_input("Quantity", min_value=0, value=int(item["quantity"]), step=1)
            condition = c3.selectbox("Condition", CONDITIONS, index=CONDITIONS.index(item["condition"]) if item["condition"] in CONDITIONS else 0)
            shelf = c4.text_input("Shelf", value=item["shelf"])
            condition_notes = st.text_area("Condition notes", value=item["condition_notes"])
            barcode = st.text_input("Barcode", value=item["barcode"])
            tags = st.text_input("Tags (comma separated)", value=item["tags"])
            c1, c2 = st.columns(2)
            vendor = c1.text_input("Vendor", value=item["vendor"])
            product_type = c2.text_input("Product type", value=item["product_type"])
            description = st.text_area("Description", value=item["description"], height=150)
            c1, c2, c3 = st.columns(3)
            review = c1.checkbox("Manual review", value=bool(item["review"]))
            ready = c2.checkbox("READY for Shopify validation", value=bool(item["ready"]))
            pool_mode = c3.selectbox("Inventory mode", POOL_MODES, index=POOL_MODES.index(item["pool_mode"]))
            if st.form_submit_button("Save item", type="primary"):
                db.update_item(
                    paths.db_file, item["item_id"],
                    {
                        "title": title, "edition": edition, "distributor": distributor,
                        "price_cents": round(price * 100), "quantity": int(quantity),
                        "condition": condition, "shelf": shelf.strip().upper(),
                        "condition_notes": condition_notes, "barcode": barcode,
                        "tags": tags, "vendor": vendor, "product_type": product_type,
                        "description": description, "review": int(review), "ready": int(ready),
                        "pool_mode": pool_mode,
                    },
                )
                validate_items(paths.db_file, [item["item_id"]])
                st.success("Saved by immutable Item ID.")
                st.rerun()

elif page == "CSV workflow":
    st.title("CSV export and re-import")
    batches = db.list_batches(paths.db_file)
    if not batches:
        st.info("Import a batch first.")
    else:
        selected = st.selectbox("Batch", [row["batch_id"] for row in batches])
        destination = paths.processed / selected / "inventory_work.csv"
        if st.button("Refresh inventory_work.csv"):
            export_inventory_csv(paths.db_file, selected, destination)
            st.success(f"Exported {destination}")
        if destination.exists():
            st.download_button(
                "Download inventory_work.csv", destination.read_bytes(),
                file_name=f"{selected}-inventory_work.csv", mime="text/csv",
            )
        uploaded = st.file_uploader("Import edited inventory_work.csv", type="csv")
        if uploaded and st.button("Validate and import CSV", type="primary"):
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as temp:
                temp.write(uploaded.getvalue())
                temp_path = Path(temp.name)
            try:
                count = import_inventory_csv(paths.db_file, temp_path, paths=paths)
                export_inventory_csv(paths.db_file, selected, destination)
                st.success(f"Updated {count} row(s) by Item ID. Row order was ignored.")
            except Exception as exc:
                st.error(str(exc))
            finally:
                temp_path.unlink(missing_ok=True)

elif page == "Validation":
    st.title("Validation")
    batches = db.list_batches(paths.db_file)
    selected = st.selectbox("Batch", [""] + [row["batch_id"] for row in batches])
    if st.button("Validate selected batch", type="primary"):
        item_ids = [item["item_id"] for item in db.list_items(paths.db_file, batch_id_value=selected or None)]
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
        ], hide_index=True, use_container_width=True,
    )

elif page == "Database":
    st.title("Database inspection and audit")
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
    st.dataframe([dict(row) for row in rows], hide_index=True, use_container_width=True)
    audit_path = paths.exports / f"inventory-events-{os.getpid()}.csv"
    if st.button("Generate inventory event audit CSV"):
        export_audit_csv(paths.db_file, audit_path)
    if audit_path.exists():
        st.download_button("Download audit CSV", audit_path.read_bytes(), file_name="inventory-events.csv")

elif page == "Recognition":
    st.title("Recognition providers")
    st.warning("Recognition produces suggestions only. Nothing becomes authoritative until you accept it.")
    providers = recognizer_registry()
    st.dataframe(
        [
            {"Provider": name, "Available": provider.available()[0], "Status": provider.available()[1]}
            for name, provider in providers.items()
        ], hide_index=True, use_container_width=True,
    )
    items = db.list_items(paths.db_file)
    if items:
        item_id_value = st.selectbox("Item", [item["item_id"] for item in items])
        provider_name = st.selectbox("Provider", list(providers))
        if st.button("Generate suggestions", type="primary"):
            try:
                result_id, result = run_recognition(paths.db_file, item_id_value, providers[provider_name])
                st.session_state["recognition_result"] = result_id
                st.json({
                    "title": result.suggested_title, "edition": result.edition,
                    "distributor": result.distributor, "confidence": result.confidence,
                    "uncertainty": result.uncertainty_reasons, "requires_review": result.requires_review,
                })
            except Exception as exc:
                st.error(str(exc))
        results = list_results(paths.db_file, item_id_value)
        if results:
            st.dataframe(results, hide_index=True, use_container_width=True)
            chosen = st.selectbox("Suggestion to accept", [row["recognition_result_id"] for row in results])
            if st.button("Accept selected fields into item"):
                accept_result(paths.db_file, chosen)
                st.success("Suggestion accepted and item marked for manual review.")

    st.divider()
    st.subheader("Batch recognition")
    batches = db.list_batches(paths.db_file)
    if not batches:
        st.info("Import a batch before running batch recognition.")
    else:
        batch_options = [row["batch_id"] for row in batches]
        batch_id_value = st.selectbox("Batch", batch_options, key="batch_recognition_batch")
        batch_provider_name = st.selectbox("Provider", list(providers), key="batch_recognition_provider")
        skip_existing = st.checkbox(
            "Skip items that already have a recognition result",
            value=True,
            key="batch_recognition_skip_existing",
        )
        only_missing_title = st.checkbox(
            "Only process items with no title",
            value=False,
            key="batch_recognition_only_missing_title",
        )
        force_reprocess = st.checkbox(
            "Force reprocess",
            value=False,
            key="batch_recognition_force_reprocess",
        )
        batch_items = db.list_items(paths.db_file, batch_id_value=batch_id_value)
        st.caption(f"{len(batch_items)} item(s) in selected batch.")
        if st.button("Recognize entire batch", type="primary", key="batch_recognition_run"):
            progress_bar = st.progress(0.0, text="Starting batch recognition…")
            status = st.empty()
            metrics = st.empty()
            failures_box = st.empty()
            live_progress: dict[str, int | str | list[dict[str, str]]] = {
                "current_item_id": "",
                "completed": 0,
                "total": len(batch_items),
                "recognized": 0,
                "review_required": 0,
                "skipped": 0,
                "failed": 0,
                "failures": [],
            }

            def update_progress(state: BatchRecognitionProgress) -> None:
                live_progress["current_item_id"] = state.current_item_id
                live_progress["completed"] = state.completed
                live_progress["total"] = state.total
                live_progress["recognized"] = state.recognized
                live_progress["review_required"] = state.review_required
                live_progress["skipped"] = state.skipped
                live_progress["failed"] = state.failed
                live_progress["failures"] = [
                    {"item_id": failure.item_id, "message": failure.message}
                    for failure in state.failures
                ]
                total = state.total or 1
                progress_bar.progress(
                    state.completed / total,
                    text=f"Processing {state.current_item_id or 'batch'} ({state.completed}/{state.total})",
                )
                status.markdown(f"**Current item:** `{state.current_item_id or '—'}`")
                metrics.markdown(
                    "\n".join(
                        [
                            f"- **Completed:** {state.completed}/{state.total}",
                            f"- **Recognized:** {state.recognized}",
                            f"- **Review required:** {state.review_required}",
                            f"- **Skipped:** {state.skipped}",
                            f"- **Failed:** {state.failed}",
                        ]
                    )
                )
                if state.failures:
                    failures_box.error(
                        "Failures:\n"
                        + "\n".join(
                            f"- `{failure.item_id}`: {failure.message}" for failure in state.failures
                        )
                    )
                else:
                    failures_box.empty()

            summary = run_batch_recognition(
                paths.db_file,
                batch_id_value,
                providers[batch_provider_name],
                skip_existing=skip_existing,
                only_missing_title=only_missing_title,
                force_reprocess=force_reprocess,
                progress_callback=update_progress,
            )
            st.session_state["batch_recognition_summary"] = {
                "batch_id": summary.batch_id,
                "total": summary.total,
                "completed": summary.completed,
                "recognized": summary.recognized,
                "review_required": summary.review_required,
                "skipped": summary.skipped,
                "failed": summary.failed,
                "failures": [
                    {"item_id": failure.item_id, "message": failure.message}
                    for failure in summary.failures
                ],
            }
            if summary.failed:
                st.warning(
                    f"Batch recognition finished with {summary.failed} failure(s). "
                    f"Recognized {summary.recognized}, skipped {summary.skipped}."
                )
            else:
                st.success(
                    f"Batch recognition finished. Recognized {summary.recognized}, "
                    f"skipped {summary.skipped}."
                )
        if "batch_recognition_summary" in st.session_state:
            st.json(st.session_state["batch_recognition_summary"])

elif page == "Shopify dry-run":
    st.title("Shopify draft queue")
    st.warning("Simulation is the default. SnapIMS never publishes products; live mode creates DRAFTS only.")
    config = ShopifyConfig.from_env()
    service = ShopifyService(paths.db_file, config)
    st.json(
        {
            "store_domain": config.store_domain or "not configured",
            "api_version": config.api_version,
            "inventory_location": config.location_id or "not configured",
            "token": "configured" if config.access_token and config.access_token != "shpat_replace_me" else "not configured",
            "mode": "SIMULATION / DRAFT ONLY",
        }
    )
    items = db.list_items(paths.db_file)
    if items:
        item_id_value = st.selectbox("Item", [item["item_id"] for item in items])
        remote_check = st.checkbox("Use credentials for read-only remote SKU check", value=False)
        if st.button("Run Shopify dry-run", type="primary"):
            report = service.dry_run(item_id_value, remote_check=remote_check)
            st.json(
                {
                    "item_id": report.item_id, "ready": report.ready, "action": report.action,
                    "images": report.image_count, "errors": report.errors, "warnings": report.warnings,
                }
            )
        with st.expander("Deliberate live DRAFT creation"):
            phrase = st.text_input("Type CREATE DRAFT to enable the write button")
            understand = st.checkbox("I understand this writes a draft product to Shopify")
            if st.button("Create Shopify DRAFT", disabled=not (understand and phrase == "CREATE DRAFT")):
                try:
                    result = service.upload_draft(item_id_value, confirmed=True)
                    st.success("Draft created. Publishing remains manual.")
                    st.json(result)
                except Exception as exc:
                    st.error(str(exc))

elif page == "Logs & warnings":
    st.title("Logs and warnings")
    batches = db.list_batches(paths.db_file)
    for batch in batches:
        warnings = json.loads(batch["warnings_json"])
        with st.expander(f"{batch['batch_id']} · {len(warnings)} warning(s)"):
            if warnings:
                for warning in warnings:
                    st.warning(warning)
            else:
                st.success("No parser warnings.")
    log_path = paths.logs / "snapims.log"
    st.subheader("Structured application log")
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
        st.code("\n".join(lines) or "Log is empty.")
    else:
        st.info("The log will appear after the first import.")
