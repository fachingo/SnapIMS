from __future__ import annotations

import pytest

from snapims import active_batch, db
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
from snapims.recognition import progress, repository
from snapims.recognition.providers import MockRecognizer
from snapims.recognition.service import run_batch_recognition


class SimulatedInterruption(RuntimeError):
    pass


@pytest.mark.parametrize("boundary", [0, 1, 2])
def test_recognition_resumes_at_every_item_boundary_without_duplicates(
    tmp_path, data_paths, boundary
) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    items = db.list_items(data_paths.db_file, batch_id_value=result.batch_id)

    def interrupt(state) -> None:
        if state.completed == boundary:
            raise SimulatedInterruption(f"stop after {boundary}")

    with pytest.raises(SimulatedInterruption):
        run_batch_recognition(
            data_paths.db_file,
            result.batch_id,
            MockRecognizer(),
            progress_callback=interrupt,
        )

    interrupted = progress.latest_job(data_paths.db_file, result.batch_id)
    assert interrupted is not None
    assert interrupted.status == "INTERRUPTED"
    assert interrupted.completed == boundary
    assert interrupted.remaining == len(items) - boundary
    if interrupted.remaining:
        action = active_batch.compute_next_action(data_paths.db_file, result.batch_id)
        assert action.label.startswith("Resume recognition")

    summary = run_batch_recognition(data_paths.db_file, result.batch_id, MockRecognizer())
    assert summary.completed == len(items)
    finished = progress.latest_job(data_paths.db_file, result.batch_id)
    assert finished is not None
    assert finished.status == "COMPLETED"
    assert finished.completed == finished.total == len(items)
    for item in items:
        successes = [
            stored
            for stored in repository.list_results_for_item(
                data_paths.db_file, item["item_id"]
            )
            if stored.result_status == repository.RESULT_SUCCEEDED
        ]
        assert len(successes) == 1


def test_progress_is_durable_and_isolated_by_batch(tmp_path, data_paths) -> None:
    first = process_batch(create_demo_batch(tmp_path / "camera-a"), paths=data_paths)
    second_source = create_demo_batch(tmp_path / "camera-b")
    product = sorted(second_source.glob("*.jpg"))[2]
    product.write_bytes(product.read_bytes() + b"distinct")
    second = process_batch(second_source, paths=data_paths)

    run_batch_recognition(data_paths.db_file, first.batch_id, MockRecognizer())
    first_job = progress.latest_job(data_paths.db_file, first.batch_id)
    assert first_job is not None
    assert progress.latest_job(data_paths.db_file, second.batch_id) is None

    run_batch_recognition(data_paths.db_file, second.batch_id, MockRecognizer())
    restarted_first = progress.latest_job(data_paths.db_file, first.batch_id)
    second_job = progress.latest_job(data_paths.db_file, second.batch_id)
    assert restarted_first == first_job
    assert second_job is not None
    assert second_job.job_id != first_job.job_id

    progress.set_review_cursor(
        data_paths.db_file, first.batch_id, repository.QUEUE_TO_REVIEW, "FIRST-ITEM"
    )
    progress.set_review_cursor(
        data_paths.db_file, second.batch_id, repository.QUEUE_TO_REVIEW, "SECOND-ITEM"
    )
    assert (
        progress.get_review_cursor(
            data_paths.db_file, first.batch_id, repository.QUEUE_TO_REVIEW
        )
        == "FIRST-ITEM"
    )
    assert (
        progress.get_review_cursor(
            data_paths.db_file, second.batch_id, repository.QUEUE_TO_REVIEW
        )
        == "SECOND-ITEM"
    )
