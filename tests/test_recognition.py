from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from snapims import db
from snapims.demo import create_demo_batch
from snapims.processor import process_batch
from snapims.recognition.providers import MockRecognizer, OpenAIRecognizer, recognizer_registry
from snapims.recognition.service import accept_result, list_results, run_recognition
from tests.conftest import create_jpeg


def _sample_payload(*, requires_review: bool = False) -> dict:
    return {
        "title": "The Goonies",
        "edition": "Clamshell",
        "distributor": "Warner Home Video",
        "year": 1986,
        "barcode_candidates": ["012345678905"],
        "confidence": 0.88,
        "uncertainty_reasons": ["Spine text partially obscured"],
        "requires_review": requires_review,
    }


def _mock_openai_response(payload: dict, *, response_id: str = "resp_test123") -> MagicMock:
    response = MagicMock()
    response.id = response_id
    response.output_text = json.dumps(payload)
    return response


def test_mock_recognizer_saves_suggestions_without_auto_accepting(tmp_path, data_paths) -> None:
    process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    item = db.list_items(data_paths.db_file)[0]
    result_id, result = run_recognition(data_paths.db_file, item["item_id"], MockRecognizer())
    assert result.provider_name == "mock"
    assert result.requires_review is True
    assert result.edition == ""
    assert result.distributor == ""
    unchanged = db.get_item(data_paths.db_file, item["item_id"])
    assert unchanged["title"] == ""
    assert list_results(data_paths.db_file, item["item_id"])[0]["recognition_result_id"] == result_id
    accept_result(data_paths.db_file, result_id)
    accepted = db.get_item(data_paths.db_file, item["item_id"])
    assert accepted["title"].startswith("Demo VHS")
    assert accepted["recognition_provider"] == "mock"
    assert accepted["review"] == 0


def test_blank_mock_modifiers_preserve_authoritative_item_values(
    tmp_path, data_paths
) -> None:
    process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    item = db.list_items(data_paths.db_file)[0]
    db.update_item(
        data_paths.db_file,
        item["item_id"],
        {
            "edition": "Authoritative edition",
            "distributor": "Authoritative distributor",
        },
    )

    result_id, result = run_recognition(
        data_paths.db_file,
        item["item_id"],
        MockRecognizer(),
    )
    accept_result(data_paths.db_file, result_id)

    accepted = db.get_item(data_paths.db_file, item["item_id"])
    assert result.edition == ""
    assert result.distributor == ""
    assert accepted is not None
    assert accepted["edition"] == "Authoritative edition"
    assert accepted["distributor"] == "Authoritative distributor"


def test_provider_registry_runs_without_api_keys(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setattr("snapims.recognition.providers._ENV_LOADED", False)
    monkeypatch.setattr("snapims.recognition.providers.load_dotenv", lambda *args, **kwargs: None)
    providers = recognizer_registry()
    assert set(providers) == {"mock", "local-ocr", "openai", "gemini"}
    assert providers["mock"].available()[0]
    assert not providers["openai"].available()[0]
    assert not providers["gemini"].available()[0]


def test_openai_recognizer_converts_structured_response(tmp_path, monkeypatch) -> None:
    image = create_jpeg(tmp_path / "front.jpg")
    mock_client = MagicMock()
    mock_client.responses.create.return_value = _mock_openai_response(_sample_payload())
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    result = OpenAIRecognizer(client=mock_client).recognize({}, [image])

    assert result.provider_name == "openai"
    assert result.suggested_title == "The Goonies"
    assert result.edition == "Clamshell"
    assert result.distributor == "Warner Home Video"
    assert result.year == 1986
    assert result.barcode_candidates == ("012345678905",)
    assert result.confidence == 0.88
    assert result.uncertainty_reasons == ("Spine text partially obscured",)
    assert result.raw_response_reference == "resp_test123"
    assert result.requires_review is True


def test_openai_recognizer_encodes_up_to_three_images(tmp_path, monkeypatch) -> None:
    images = [
        create_jpeg(tmp_path / f"photo-{index}.jpg", color=color)
        for index, color in enumerate(["red", "green", "blue", "yellow"])
    ]
    mock_client = MagicMock()
    mock_client.responses.create.return_value = _mock_openai_response(_sample_payload())
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    OpenAIRecognizer(client=mock_client).recognize({}, images)

    request_input = mock_client.responses.create.call_args.kwargs["input"]
    content = request_input[0]["content"]
    image_parts = [part for part in content if part["type"] == "input_image"]
    assert len(image_parts) == 3
    for part in image_parts:
        assert part["image_url"].startswith("data:image/jpeg;base64,")


def test_openai_recognizer_missing_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    recognizer = OpenAIRecognizer()
    available, reason = recognizer.available()
    assert available is False
    assert "OPENAI_API_KEY" in reason
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        recognizer.recognize({}, [])


def test_openai_recognizer_rejects_missing_images(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with pytest.raises(ValueError, match="At least one item image"):
        OpenAIRecognizer(client=MagicMock()).recognize({}, [])


def test_openai_recognizer_rejects_invalid_image_extension(tmp_path, monkeypatch) -> None:
    bad_image = tmp_path / "notes.txt"
    bad_image.write_text("not an image", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with pytest.raises(ValueError, match="Unsupported image extension"):
        OpenAIRecognizer(client=MagicMock()).recognize({}, [bad_image])


def test_openai_recognizer_rejects_malformed_model_response(tmp_path, monkeypatch) -> None:
    image = create_jpeg(tmp_path / "front.jpg")
    mock_client = MagicMock()
    mock_client.responses.create.return_value = _mock_openai_response({"title": "Only title"})
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with pytest.raises(ValueError, match="missing fields"):
        OpenAIRecognizer(client=mock_client).recognize({}, [image])


def test_openai_recognizer_forces_requires_review_true(tmp_path, monkeypatch) -> None:
    image = create_jpeg(tmp_path / "front.jpg")
    mock_client = MagicMock()
    mock_client.responses.create.return_value = _mock_openai_response(
        _sample_payload(requires_review=False)
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    result = OpenAIRecognizer(client=mock_client).recognize({}, [image])

    assert result.requires_review is True


def test_openai_recognizer_maps_authentication_failure(tmp_path, monkeypatch) -> None:
    from openai import AuthenticationError

    image = create_jpeg(tmp_path / "front.jpg")
    mock_client = MagicMock()
    mock_client.responses.create.side_effect = AuthenticationError(
        "invalid key", response=MagicMock(), body=None
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with pytest.raises(RuntimeError, match="authentication failed"):
        OpenAIRecognizer(client=mock_client).recognize({}, [image])
