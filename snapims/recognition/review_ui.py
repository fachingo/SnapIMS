from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

import streamlit as st

from snapims import active_batch, db
from snapims.config import DataPaths
from snapims.inventory import CONDITIONS, POOL_MODES, validate_items
from snapims.recognition import progress as durable_progress
from snapims.recognition import repository
from snapims.recognition.keyboard import keyboard_shortcut_event
from snapims.recognition.providers import recognizer_registry
from snapims.recognition.review import (
    ACTION_ACCEPT,
    ACTION_ACCEPT_EDITED,
    ACTION_CANCEL_EDIT,
    ACTION_DISCARD,
    ACTION_EDIT,
    ACTION_PHOTO_PREFIX,
    ACTION_PREVIOUS,
    ACTION_RETRY,
    ACTION_SKIP,
    current_item_id,
    keyboard_decision,
    next_item_id,
    previous_item_id,
)
from snapims.recognition.service import (
    accept_edited_result,
    accept_result,
    correct_item_location,
    mark_result_for_review,
    retry_recognition,
    run_batch_recognition,
    skip_result,
)


def _stage_label(result: repository.StoredRecognitionResult) -> str:
    """One operator-facing recognition stage (never publish/upload language)."""
    if result.result_status == repository.RESULT_FAILED:
        return repository.QUEUE_FAILED
    if result.review_status == repository.REVIEW_ACCEPTED:
        return repository.QUEUE_DONE
    if result.review_status in (repository.REVIEW_REQUIRED, repository.REVIEW_REJECTED):
        return repository.QUEUE_NEEDS_ATTENTION
    return repository.QUEUE_TO_REVIEW


def _provider_name(providers: dict[str, Any]) -> str:
    state_key = "recognition_provider_name"
    current = st.session_state.get(state_key)
    if current not in providers:
        current = "openai" if providers["openai"].available()[0] else "mock"
        st.session_state[state_key] = current
    return str(current)


def _compact_provider(providers: dict[str, Any]) -> str:
    state_key = "recognition_provider_name"
    current = _provider_name(providers)
    st.caption(f"Provider: `{current}`")
    if st.button("Change", key="review_change_provider"):
        st.session_state["review_provider_picker_visible"] = not st.session_state.get(
            "review_provider_picker_visible",
            False,
        )
    if st.session_state.get("review_provider_picker_visible", False):
        selected = st.selectbox(
            "Provider",
            list(providers),
            index=list(providers).index(current),
            key="review_provider_choice",
            label_visibility="collapsed",
        )
        st.session_state[state_key] = selected
        current = selected
    return str(current)


def _shortcut_strip() -> None:
    st.markdown(
        """
        <div class="shortcut-strip">
          <b>Enter</b> Accept & next
          <b>→</b> Later
          <b>←</b> Previous
          <b>E</b> Edit
          <b>Esc</b> Cancel edit
          <b>⌘/Ctrl+Enter</b> Save edit
          <b>1–9</b> Photo
          <b>F</b> Retry (failed only)
        </div>
        """,
        unsafe_allow_html=True,
    )


def _set_next(queue_item_ids: list[str], current_item_id_value: str) -> None:
    st.session_state["review_preferred_item_id"] = next_item_id(
        queue_item_ids,
        current_item_id_value,
    )
    st.session_state["review_edit_mode"] = False


def _edited_values(result_id: int) -> dict[str, Any]:
    year = st.session_state.get(f"review_year_{result_id}")
    release_year = None if year in (None, "") else int(str(year))
    price = st.session_state.get(f"review_price_{result_id}")
    return {
        "title": st.session_state.get(f"review_title_{result_id}", ""),
        "edition": st.session_state.get(f"review_edition_{result_id}", ""),
        "distributor": st.session_state.get(f"review_distributor_{result_id}", ""),
        "release_year": release_year,
        "barcode": st.session_state.get(f"review_barcode_{result_id}", ""),
        "price_cents": round(float(price) * 100) if price is not None else None,
        "condition": st.session_state.get(f"review_condition_{result_id}", "Not Graded"),
        "quantity": int(st.session_state.get(f"review_quantity_{result_id}", 1)),
        "ready": int(bool(st.session_state.get(f"review_ready_{result_id}", False))),
    }


def _perform_action(
    action: str,
    *,
    db_file: Path,
    entry: repository.ReviewQueueEntry,
    queue_item_ids: list[str],
    provider_name: str,
) -> None:
    result_id = entry.result.recognition_result_id
    item_id = entry.result.item_id
    if action.startswith(ACTION_PHOTO_PREFIX):
        st.session_state[f"review_photo_{entry.result.item_id}"] = int(
            action.removeprefix(ACTION_PHOTO_PREFIX)
        )
        st.rerun()
    if action == ACTION_PREVIOUS:
        st.session_state["review_preferred_item_id"] = previous_item_id(
            queue_item_ids,
            item_id,
        )
        st.session_state["review_edit_mode"] = False
        st.rerun()
    if action == ACTION_EDIT:
        st.session_state["review_edit_mode"] = True
        st.rerun()
    if action == ACTION_CANCEL_EDIT:
        st.session_state["review_edit_mode"] = False
        st.rerun()

    st.session_state["review_busy"] = True
    try:
        if action == ACTION_ACCEPT:
            with st.spinner("Accepting suggestion…"):
                errors = accept_result(db_file, result_id)
                st.session_state["review_last_validation"] = {
                    "item_id": item_id,
                    "errors": errors,
                }
        elif action == ACTION_ACCEPT_EDITED:
            with st.spinner("Saving edited metadata…"):
                errors = accept_edited_result(
                    db_file,
                    result_id,
                    _edited_values(result_id),
                )
                st.session_state["review_last_validation"] = {
                    "item_id": item_id,
                    "errors": errors,
                }
        elif action == ACTION_SKIP:
            skip_result(db_file, result_id)
        elif action == ACTION_DISCARD:
            mark_result_for_review(db_file, result_id)
        elif action == ACTION_RETRY:
            providers = recognizer_registry()
            with st.spinner(f"Retrying with {provider_name}…"):
                retry_recognition(
                    db_file,
                    entry.result.item_id,
                    providers[provider_name],
                )
        else:
            return
        _set_next(queue_item_ids, item_id)
    finally:
        st.session_state["review_busy"] = False
    st.rerun()


def _render_photos(db_file: Path, item_id: str) -> None:
    photos = db.get_item_photos(db_file, item_id)[:9]
    if not photos:
        st.warning("No item photos are available.")
        return
    photo_key = f"review_photo_{item_id}"
    selected = min(int(st.session_state.get(photo_key, 0)), len(photos) - 1)
    st.session_state[photo_key] = selected
    main_path = photos[selected]["processed_path"]
    st.markdown('<div class="review-cover">', unsafe_allow_html=True)
    st.image(
        main_path,
        caption=f"Photo {selected + 1} of {len(photos)}",
        width="stretch",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    columns = st.columns(len(photos), gap="small")
    for index, (column, photo) in enumerate(zip(columns, photos, strict=True)):
        with column:
            thumbnail = photo["thumbnail_path"] or photo["processed_path"]
            st.image(thumbnail, width="stretch")
            if st.button(
                str(index + 1),
                key=f"review_thumb_{item_id}_{index}",
                type="primary" if index == selected else "secondary",
                width="stretch",
            ):
                st.session_state[photo_key] = index
                st.rerun()


def _render_status(entry: repository.ReviewQueueEntry, position: int, total: int) -> None:
    result = entry.result
    status = _stage_label(result)
    status_class = status.lower().replace(" ", "-")
    st.markdown(
        f"""
        <div class="review-heading">
          <span class="status-badge {status_class}">{escape(status)}</span>
          <span class="queue-position">{position} / {total}</span>
        </div>
        <div class="item-context">
          <b>{escape(result.item_id)}</b><br>
          Batch {escape(result.batch_id)} · Shelf {escape(entry.shelf)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_suggestion(entry: repository.ReviewQueueEntry, edit_mode: bool) -> None:
    result = entry.result
    if result.result_status == repository.RESULT_FAILED:
        st.error(result.error_message or "Recognition failed without an error message.")
    barcode = result.barcode_candidates[0] if result.barcode_candidates else ""
    if edit_mode:
        st.text_input(
            "Title",
            value=result.suggested_title,
            key=f"review_title_{result.recognition_result_id}",
        )
        first, second = st.columns(2)
        first.number_input(
            "Release year",
            min_value=0,
            max_value=9999,
            value=result.release_year,
            placeholder="Unknown",
            key=f"review_year_{result.recognition_result_id}",
        )
        second.text_input(
            "Barcode",
            value=barcode,
            key=f"review_barcode_{result.recognition_result_id}",
        )
        st.text_input(
            "Distributor / studio",
            value=result.distributor,
            key=f"review_distributor_{result.recognition_result_id}",
        )
        st.text_input(
            "Edition / format",
            value=result.edition,
            key=f"review_edition_{result.recognition_result_id}",
        )
        price_column, condition_column, quantity_column = st.columns(3)
        price_column.number_input(
            "Price",
            min_value=0.0,
            value=0.0 if entry.price_cents is None else entry.price_cents / 100,
            step=1.0,
            key=f"review_price_{result.recognition_result_id}",
        )
        condition_column.selectbox(
            "Condition",
            CONDITIONS,
            index=(
                CONDITIONS.index(entry.condition)
                if entry.condition in CONDITIONS
                else 0
            ),
            key=f"review_condition_{result.recognition_result_id}",
        )
        quantity_column.number_input(
            "Quantity",
            min_value=0,
            value=entry.quantity,
            step=1,
            key=f"review_quantity_{result.recognition_result_id}",
        )
        st.checkbox(
            "Ready for draft",
            value=entry.ready,
            key=f"review_ready_{result.recognition_result_id}",
        )
        st.caption("Ctrl+Enter saves these values. Escape discards edit mode.")
        return

    confidence_percent = round(result.confidence * 100)
    st.markdown(
        f"""
        <div class="suggestion-title">{escape(result.suggested_title or "No title suggested")}</div>
        <div class="metadata-grid">
          <div><span>Year</span><b>{result.release_year or "—"}</b></div>
          <div><span>Studio</span><b>{escape(result.distributor or "—")}</b></div>
          <div><span>Barcode</span><b>{escape(barcode or "—")}</b></div>
          <div><span>Edition / format</span><b>{escape(result.edition or "—")}</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(result.confidence, text=f"Overall confidence · {confidence_percent}%")
    st.markdown("**Uncertainty**")
    if result.uncertainty_reasons:
        st.warning(" · ".join(result.uncertainty_reasons))
    else:
        st.caption("No uncertainty noted.")
    price = "—" if entry.price_cents is None else f"${entry.price_cents / 100:.2f}"
    physical_review = "Yes" if entry.physical_review else "No"
    rare = "Yes" if entry.rare else "No"
    readiness = (
        "Ready for draft"
        if entry.validation_status == "READY"
        else entry.validation_status.title()
    )
    st.markdown(
        f"""
        <div class="metadata-grid">
          <div><span>Price</span><b>{price}</b></div>
          <div><span>Condition</span><b>{escape(entry.condition)}</b></div>
          <div><span>Quantity</span><b>{entry.quantity}</b></div>
          <div><span>Shelf</span><b>{escape(entry.shelf)}</b></div>
          <div><span>Rare</span><b>{rare}</b></div>
          <div><span>Physical review</span><b>{physical_review}</b></div>
          <div class="wide"><span>Validation</span><b>{escape(readiness)}</b></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if entry.validation_errors:
        st.error("\n".join(f"• {error}" for error in entry.validation_errors))
    elif entry.validation_status == "READY":
        st.success("Ready for draft")


def render_batch_details_section(db_file: Path, batch_id_value: str) -> None:
    """Human-readable item grouping/timeline for one batch.

    Raw command-stream evidence (QR payload, stream index, command kind,
    source photo) is intentionally excluded here; that raw evidence
    remains reachable under Settings & diagnostics.
    """
    batch = db.get_batch(db_file, batch_id_value)
    if batch is None:
        return
    with st.expander(f"Batch details · {batch_id_value}", expanded=False):
        columns = st.columns(3)
        columns[0].metric("Items", batch["item_count"])
        columns[1].metric("Product images", batch["product_photo_count"])
        columns[2].metric("Warnings", batch["warning_count"])
        items = db.list_items(db_file, batch_id_value=batch_id_value)
        st.dataframe(
            [
                {
                    "Sequence": item["sequence"],
                    "Shelf": item["shelf"],
                    "Title": item["title"] or "Untitled VHS",
                    "Images": item["image_count"],
                    "Rare": bool(item["rare"]),
                    "Review": bool(item["review"]),
                }
                for item in items
            ],
            hide_index=True,
            width="stretch",
        )
        warnings = json.loads(batch["warnings_json"])
        if warnings:
            st.warning("\n".join(warnings))
        else:
            st.caption("No parser warnings for this batch.")


def _queue_for_item(db_file: Path, item_id_value: str) -> str:
    stored = repository.latest_result_for_item(db_file, item_id_value)
    if stored is None:
        return repository.QUEUE_TO_REVIEW
    if stored.result_status == repository.RESULT_FAILED:
        return repository.QUEUE_FAILED
    if stored.review_status == repository.REVIEW_ACCEPTED:
        return repository.QUEUE_DONE
    if stored.review_status in (repository.REVIEW_REQUIRED, repository.REVIEW_REJECTED):
        return repository.QUEUE_NEEDS_ATTENTION
    return repository.QUEUE_TO_REVIEW


def _overview_status_label(db_file: Path, item_id_value: str) -> str:
    stored = repository.latest_result_for_item(db_file, item_id_value)
    if stored is None:
        return "Not yet recognized"
    return _stage_label(stored)


def _run_batch_recognition_with_progress(
    db_file: Path,
    batch_id_value: str,
    recognizer: Any,
    *,
    skip_existing: bool,
    only_missing_title: bool,
    force_reprocess: bool,
) -> None:
    progress_bar = st.progress(0.0, text="Starting batch recognition…")
    status = st.empty()
    metrics = st.empty()
    failures_box = st.empty()

    def update_progress(state: Any) -> None:
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
                + "\n".join(f"- `{failure.item_id}`: {failure.message}" for failure in state.failures)
            )
        else:
            failures_box.empty()

    summary = run_batch_recognition(
        db_file,
        batch_id_value,
        recognizer,
        skip_existing=skip_existing,
        only_missing_title=only_missing_title,
        force_reprocess=force_reprocess,
        progress_callback=update_progress,
    )
    st.session_state["review_recognition_summary"] = {
        "batch_id": summary.batch_id,
        "recognized": summary.recognized,
        "review_required": summary.review_required,
        "skipped": summary.skipped,
        "failed": summary.failed,
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


def _render_recognition_overview(
    paths: DataPaths, batch_id_value: str, providers: dict[str, Any]
) -> str:
    st.subheader("Review overview")
    items = db.list_items(paths.db_file, batch_id_value=batch_id_value)
    if not items:
        st.info("This batch has no items yet.")
        return _provider_name(providers)

    provider_col, options_col = st.columns([1, 3])
    with provider_col:
        provider_name = _compact_provider(providers)
    with options_col, st.expander("Advanced", expanded=False):
        st.caption("Safe resume always skips items with a successful recognition result.")
        skip_existing = True
        only_missing_title = st.checkbox(
            "Only process items with no title",
            value=False,
            key="review_overview_only_missing_title",
        )
        force_reprocess = st.checkbox(
            "Force reprocess",
            value=False,
            key="review_overview_force_reprocess",
        )
    unattempted = sum(
        1
        for item in items
        if repository.latest_result_for_item(paths.db_file, item["item_id"]) is None
    )
    durable_job = durable_progress.latest_job(paths.db_file, batch_id_value)
    action_label = "Start recognition" if unattempted == len(items) else "Resume recognition"
    if st.button(action_label, type="primary", key="review_overview_run_recognition"):
        _run_batch_recognition_with_progress(
            paths.db_file,
            batch_id_value,
            providers[provider_name],
            skip_existing=skip_existing,
            only_missing_title=only_missing_title,
            force_reprocess=force_reprocess,
        )

    summary = st.session_state.get("review_recognition_summary")
    if durable_job is not None:
        st.info(
            f"Resume: {durable_job.completed}/{durable_job.total} completed · "
            f"{durable_job.remaining} remaining · {durable_job.failed} failed"
        )
    if summary and summary["batch_id"] == batch_id_value:
        metric_columns = st.columns(4)
        for column, label, key in zip(
            metric_columns,
            ("Recognized", "Review required", "Skipped", "Failed"),
            ("recognized", "review_required", "skipped", "failed"),
            strict=True,
        ):
            column.metric(label, summary[key])

    st.caption("Click a card to open that item in the workstation below.")
    columns = st.columns(4)
    for index, item in enumerate(items):
        with columns[index % 4]:
            st.markdown('<div class="snap-card">', unsafe_allow_html=True)
            if item["front_thumbnail"]:
                st.image(item["front_thumbnail"], width="stretch")
            st.markdown(f"**{item['title'] or 'Untitled VHS'}**")
            st.caption(f"{item['item_id']} · Shelf {item['shelf']}")
            flags = [name for name, value in (("RARE", item["rare"]), ("REVIEW", item["review"])) if value]
            if flags:
                st.warning(" · ".join(flags))
            st.caption(_overview_status_label(paths.db_file, item["item_id"]))
            if st.button("Open", key=f"review_overview_open_{item['item_id']}", width="stretch"):
                st.session_state["review_open_item_id"] = item["item_id"]
                st.session_state["review_filter"] = _queue_for_item(paths.db_file, item["item_id"])
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
    st.divider()
    return provider_name


def _render_more(
    db_file: Path,
    entry: repository.ReviewQueueEntry,
    queue_item_ids: list[str],
    provider_name: str,
) -> None:
    item_id_value = entry.result.item_id
    item = db.get_item(db_file, item_id_value)
    if item is None:
        return
    can_discard = (
        entry.result.result_status == repository.RESULT_SUCCEEDED
        and entry.result.review_status != repository.REVIEW_ACCEPTED
    )
    with st.expander("More", expanded=False):
        if can_discard:
            st.caption(
                "Discard suggestion leaves this item reachable in Needs attention."
            )
            if st.button(
                "Discard suggestion",
                key=f"review_discard_{item_id_value}",
                width="stretch",
            ):
                _perform_action(
                    ACTION_DISCARD,
                    db_file=db_file,
                    entry=entry,
                    queue_item_ids=queue_item_ids,
                    provider_name=provider_name,
                )
            st.divider()
        st.caption("Advanced item fields, moved here from the former Item editor page.")
        with st.form(f"review_more_{item_id_value}"):
            first, second = st.columns(2)
            vendor = first.text_input("Vendor", value=item["vendor"])
            product_type = second.text_input("Product type", value=item["product_type"])
            tags = st.text_input("Tags (comma separated)", value=item["tags"])
            condition_notes = st.text_area("Condition notes", value=item["condition_notes"])
            description = st.text_area("Description", value=item["description"], height=120)
            pool_mode = st.selectbox(
                "Inventory mode",
                POOL_MODES,
                index=POOL_MODES.index(item["pool_mode"]) if item["pool_mode"] in POOL_MODES else 0,
            )
            physical_review = st.checkbox(
                "Physical REVIEW flag (manual override)", value=bool(item["review"])
            )
            if st.form_submit_button("Save advanced fields"):
                db.update_item(
                    db_file,
                    item_id_value,
                    {
                        "vendor": vendor,
                        "product_type": product_type,
                        "tags": tags,
                        "condition_notes": condition_notes,
                        "description": description,
                        "pool_mode": pool_mode,
                        "review": int(physical_review),
                    },
                )
                validate_items(db_file, [item_id_value])
                st.success("Saved advanced fields.")
                st.rerun()
        st.divider()
        st.caption(
            "Shelf is display-only above. Correcting the location requires a "
            "valid shelf (A1-J10 or Q1) and a reason, and always records one "
            "auditable inventory event."
        )
        with st.form(f"review_correct_location_{item_id_value}"):
            new_shelf = st.text_input("New shelf", value=item["shelf"])
            reason = st.text_input("Reason for correction")
            if st.form_submit_button("Correct location"):
                try:
                    correct_item_location(db_file, item_id_value, new_shelf, reason)
                except (ValueError, KeyError) as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Shelf corrected to {new_shelf.strip().upper()}.")
                    st.rerun()


def render_review(paths: DataPaths) -> None:
    st.title("Review")
    batches = db.list_batches(paths.db_file)
    if not batches:
        st.info("Import a batch before opening the review workstation.")
        return

    batch_options = [batch["batch_id"] for batch in batches]
    active = active_batch.get_active_batch(paths.db_file)
    default_index = (
        batch_options.index(active["batch_id"])
        if active and active["batch_id"] in batch_options
        else 0
    )
    batch_id = st.selectbox(
        "Batch",
        batch_options,
        index=default_index,
        key="review_batch",
    )
    render_batch_details_section(paths.db_file, batch_id)

    providers = recognizer_registry()
    provider_name = _render_recognition_overview(paths, batch_id, providers)

    _shortcut_strip()
    queue_filter = st.selectbox(
        "Queue",
        repository.QUEUE_FILTERS,
        key="review_filter",
    )
    queue = repository.list_review_queue(paths.db_file, batch_id, queue_filter)
    if not queue:
        st.success(f"No items in “{queue_filter}” for this batch.")
        return

    queue_item_ids = [entry.result.item_id for entry in queue]
    requested = st.session_state.pop("review_open_item_id", None)
    persisted = durable_progress.get_review_cursor(paths.db_file, batch_id, queue_filter)
    preferred = requested or st.session_state.get("review_preferred_item_id") or persisted
    selected_item = current_item_id(queue_item_ids, preferred)
    if selected_item is None:
        return
    st.session_state["review_preferred_item_id"] = selected_item
    durable_progress.set_review_cursor(paths.db_file, batch_id, queue_filter, selected_item)
    entry = next(item for item in queue if item.result.item_id == selected_item)
    position = queue_item_ids.index(selected_item) + 1
    edit_mode = bool(st.session_state.get("review_edit_mode", False))
    busy = bool(st.session_state.get("review_busy", False))

    is_failed = entry.result.result_status == repository.RESULT_FAILED
    is_accepted = entry.result.review_status == repository.REVIEW_ACCEPTED
    event = keyboard_shortcut_event(key=f"review_keyboard_{selected_item}")
    decision = keyboard_decision(
        event,
        last_event_id=str(st.session_state.get("review_last_keyboard_event", "")),
        edit_mode=edit_mode,
        is_failed=is_failed,
        is_accepted=is_accepted,
    )
    st.session_state["review_last_keyboard_event"] = decision.event_id
    if decision.action:
        _perform_action(
            decision.action,
            db_file=paths.db_file,
            entry=entry,
            queue_item_ids=queue_item_ids,
            provider_name=provider_name,
        )

    left, right = st.columns([1.12, 1], gap="medium")
    with left:
        _render_photos(paths.db_file, entry.result.item_id)
    with right:
        _render_status(entry, position, len(queue))
        _render_suggestion(entry, edit_mode)
        if edit_mode:
            save, cancel = st.columns(2)
            if save.button(
                "Save edits & next",
                type="primary",
                width="stretch",
                disabled=busy,
            ):
                _perform_action(
                    ACTION_ACCEPT_EDITED,
                    db_file=paths.db_file,
                    entry=entry,
                    queue_item_ids=queue_item_ids,
                    provider_name=provider_name,
                )
            if cancel.button("Cancel edit", width="stretch", disabled=busy):
                _perform_action(
                    ACTION_CANCEL_EDIT,
                    db_file=paths.db_file,
                    entry=entry,
                    queue_item_ids=queue_item_ids,
                    provider_name=provider_name,
                )
        else:
            if is_failed:
                if st.button("Retry", type="primary", width="stretch", disabled=busy):
                    try:
                        _perform_action(
                            ACTION_RETRY,
                            db_file=paths.db_file,
                            entry=entry,
                            queue_item_ids=queue_item_ids,
                            provider_name=provider_name,
                        )
                    except Exception as exc:
                        st.error(str(exc))
            elif not is_accepted:
                accept_col, edit_col, later_col = st.columns(3)
                if accept_col.button(
                    "Accept & next",
                    type="primary",
                    width="stretch",
                    disabled=busy,
                ):
                    _perform_action(
                        ACTION_ACCEPT,
                        db_file=paths.db_file,
                        entry=entry,
                        queue_item_ids=queue_item_ids,
                        provider_name=provider_name,
                    )
                if edit_col.button("Edit", width="stretch", disabled=busy):
                    _perform_action(
                        ACTION_EDIT,
                        db_file=paths.db_file,
                        entry=entry,
                        queue_item_ids=queue_item_ids,
                        provider_name=provider_name,
                    )
                if later_col.button("Later", width="stretch", disabled=busy):
                    _perform_action(
                        ACTION_SKIP,
                        db_file=paths.db_file,
                        entry=entry,
                        queue_item_ids=queue_item_ids,
                        provider_name=provider_name,
                    )
            if st.button(
                "← Previous",
                width="stretch",
                disabled=busy,
                key=f"review_previous_{entry.result.item_id}",
            ):
                _perform_action(
                    ACTION_PREVIOUS,
                    db_file=paths.db_file,
                    entry=entry,
                    queue_item_ids=queue_item_ids,
                    provider_name=provider_name,
                )
        _render_more(paths.db_file, entry, queue_item_ids, provider_name)
        with st.expander("Details", expanded=False):
            st.caption(f"Result ID: {entry.result.recognition_result_id}")
            st.caption(
                f"Provider: {entry.result.provider} · Model: "
                f"{entry.result.model_name or 'not recorded'}"
            )
            st.caption(f"Created: {entry.result.created_at}")
            st.caption(
                "Response reference: "
                f"{entry.result.raw_response_reference or 'not recorded'}"
            )
