from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

import streamlit as st

from snapims import db
from snapims.config import DataPaths
from snapims.recognition import repository
from snapims.recognition.keyboard import keyboard_shortcut_event
from snapims.recognition.providers import recognizer_registry
from snapims.recognition.review import (
    ACTION_ACCEPT,
    ACTION_ACCEPT_EDITED,
    ACTION_CANCEL_EDIT,
    ACTION_EDIT,
    ACTION_MANUAL_REVIEW,
    ACTION_PHOTO_PREFIX,
    ACTION_PREVIOUS,
    ACTION_RETRY,
    ACTION_SKIP,
    current_result_id,
    keyboard_decision,
    next_result_id,
    previous_result_id,
)
from snapims.recognition.service import (
    accept_edited_result,
    accept_result,
    mark_result_for_review,
    reject_result,
    retry_recognition,
    skip_result,
)

_STATUS_LABELS = {
    repository.REVIEW_UNREVIEWED: "Unreviewed",
    repository.REVIEW_REQUIRED: "Review required",
    repository.REVIEW_ACCEPTED: "Accepted",
    repository.REVIEW_REJECTED: "Rejected",
    repository.REVIEW_SKIPPED: "Skipped",
    repository.REVIEW_FAILED: "Failed",
}


def _compact_provider(providers: dict[str, Any]) -> str:
    state_key = "recognition_provider_name"
    current = st.session_state.get(state_key)
    if current not in providers:
        current = "openai" if providers["openai"].available()[0] else "mock"
        st.session_state[state_key] = current
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
          <b>Enter</b> Accept
          <b>→</b> Skip
          <b>←</b> Previous
          <b>R</b> Manual review
          <b>E</b> Edit
          <b>Esc</b> Cancel edit
          <b>⌘/Ctrl+Enter</b> Save edit
          <b>1–9</b> Photo
          <b>F</b> Retry
        </div>
        """,
        unsafe_allow_html=True,
    )


def _set_next(queue_ids: list[int], current_id: int) -> None:
    st.session_state["review_preferred_result_id"] = next_result_id(queue_ids, current_id)
    st.session_state["review_edit_mode"] = False


def _edited_values(result_id: int) -> dict[str, Any]:
    year = st.session_state.get(f"review_year_{result_id}")
    release_year = None if year in (None, "") else int(str(year))
    return {
        "title": st.session_state.get(f"review_title_{result_id}", ""),
        "edition": st.session_state.get(f"review_edition_{result_id}", ""),
        "distributor": st.session_state.get(f"review_distributor_{result_id}", ""),
        "release_year": release_year,
        "barcode": st.session_state.get(f"review_barcode_{result_id}", ""),
    }


def _perform_action(
    action: str,
    *,
    db_file: Path,
    entry: repository.ReviewQueueEntry,
    queue_ids: list[int],
    provider_name: str,
) -> None:
    result_id = entry.result.recognition_result_id
    if action.startswith(ACTION_PHOTO_PREFIX):
        st.session_state[f"review_photo_{entry.result.item_id}"] = int(
            action.removeprefix(ACTION_PHOTO_PREFIX)
        )
        st.rerun()
    if action == ACTION_PREVIOUS:
        st.session_state["review_preferred_result_id"] = previous_result_id(
            queue_ids, result_id
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
                accept_result(db_file, result_id)
        elif action == ACTION_ACCEPT_EDITED:
            with st.spinner("Saving edited metadata…"):
                accept_edited_result(db_file, result_id, _edited_values(result_id))
        elif action == ACTION_SKIP:
            skip_result(db_file, result_id)
        elif action == ACTION_MANUAL_REVIEW:
            mark_result_for_review(db_file, result_id)
        elif action == "reject":
            reject_result(db_file, result_id)
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
        _set_next(queue_ids, result_id)
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
    status = (
        "Failed"
        if result.result_status == repository.RESULT_FAILED
        else _STATUS_LABELS.get(result.review_status, result.review_status.title())
    )
    status_class = status.lower().replace(" ", "-")
    review_badge = (
        '<span class="status-badge review-required">Review required</span>'
        if result.requires_review and status == "Unreviewed"
        else ""
    )
    st.markdown(
        f"""
        <div class="review-heading">
          <span class="status-badge {status_class}">{escape(status)}</span>
          {review_badge}
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
        return
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


def render_review(paths: DataPaths) -> None:
    st.title("Review")
    _shortcut_strip()
    batches = db.list_batches(paths.db_file)
    if not batches:
        st.info("Import and recognize a batch before opening the review workstation.")
        return

    controls = st.columns([1.35, 1.1, 0.9])
    batch_id = controls[0].selectbox(
        "Batch",
        [batch["batch_id"] for batch in batches],
        key="review_batch",
    )
    queue_filter = controls[1].selectbox(
        "Queue",
        repository.QUEUE_FILTERS,
        key="review_filter",
    )
    providers = recognizer_registry()
    with controls[2]:
        provider_name = _compact_provider(providers)
    queue = repository.list_review_queue(paths.db_file, batch_id, queue_filter)
    if not queue:
        st.success(f"No items in “{queue_filter}” for this batch.")
        return

    queue_ids = [entry.result.recognition_result_id for entry in queue]
    requested = st.session_state.pop("review_open_result_id", None)
    preferred = requested or st.session_state.get("review_preferred_result_id")
    selected_id = current_result_id(queue_ids, preferred)
    if selected_id is None:
        return
    st.session_state["review_preferred_result_id"] = selected_id
    entry = next(item for item in queue if item.result.recognition_result_id == selected_id)
    position = queue_ids.index(selected_id) + 1
    edit_mode = bool(st.session_state.get("review_edit_mode", False))
    busy = bool(st.session_state.get("review_busy", False))

    event = keyboard_shortcut_event(key=f"review_keyboard_{selected_id}")
    decision = keyboard_decision(
        event,
        last_event_id=str(st.session_state.get("review_last_keyboard_event", "")),
        edit_mode=edit_mode,
    )
    st.session_state["review_last_keyboard_event"] = decision.event_id
    if decision.action:
        _perform_action(
            decision.action,
            db_file=paths.db_file,
            entry=entry,
            queue_ids=queue_ids,
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
                    queue_ids=queue_ids,
                    provider_name=provider_name,
                )
            if cancel.button("Cancel edit", width="stretch", disabled=busy):
                _perform_action(
                    ACTION_CANCEL_EDIT,
                    db_file=paths.db_file,
                    entry=entry,
                    queue_ids=queue_ids,
                    provider_name=provider_name,
                )
        else:
            failed = entry.result.result_status == repository.RESULT_FAILED
            accept_col, skip_col, review_col = st.columns(3)
            if accept_col.button(
                "Accept",
                type="primary",
                width="stretch",
                disabled=busy or failed,
            ):
                _perform_action(
                    ACTION_ACCEPT,
                    db_file=paths.db_file,
                    entry=entry,
                    queue_ids=queue_ids,
                    provider_name=provider_name,
                )
            if skip_col.button(
                "Skip",
                width="stretch",
                disabled=busy or failed,
            ):
                _perform_action(
                    ACTION_SKIP,
                    db_file=paths.db_file,
                    entry=entry,
                    queue_ids=queue_ids,
                    provider_name=provider_name,
                )
            if review_col.button(
                "Manual review",
                width="stretch",
                disabled=busy or failed,
            ):
                _perform_action(
                    ACTION_MANUAL_REVIEW,
                    db_file=paths.db_file,
                    entry=entry,
                    queue_ids=queue_ids,
                    provider_name=provider_name,
                )
            previous_col, edit_col, retry_col, reject_col = st.columns(4)
            if previous_col.button("← Previous", width="stretch", disabled=busy):
                _perform_action(
                    ACTION_PREVIOUS,
                    db_file=paths.db_file,
                    entry=entry,
                    queue_ids=queue_ids,
                    provider_name=provider_name,
                )
            if edit_col.button(
                "Edit",
                width="stretch",
                disabled=busy or failed,
            ):
                _perform_action(
                    ACTION_EDIT,
                    db_file=paths.db_file,
                    entry=entry,
                    queue_ids=queue_ids,
                    provider_name=provider_name,
                )
            if retry_col.button("Retry", width="stretch", disabled=busy):
                try:
                    _perform_action(
                        ACTION_RETRY,
                        db_file=paths.db_file,
                        entry=entry,
                        queue_ids=queue_ids,
                        provider_name=provider_name,
                    )
                except Exception as exc:
                    st.error(str(exc))
            if reject_col.button(
                "Reject",
                width="stretch",
                disabled=busy or failed,
            ):
                _perform_action(
                    "reject",
                    db_file=paths.db_file,
                    entry=entry,
                    queue_ids=queue_ids,
                    provider_name=provider_name,
                )
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
