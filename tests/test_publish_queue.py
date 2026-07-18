from __future__ import annotations

from pathlib import Path
from typing import Any

from snapims import db
from snapims.config import ShopifyConfig
from snapims.demo import create_demo_batch
from snapims.inventory import validate_items
from snapims.processor import process_batch
from snapims.shopify.client import ShopifyClient
from snapims.shopify.publish import (
    build_publish_queue,
    create_selected_drafts,
    simulate_selected,
)
from snapims.shopify.service import ShopifyService
from tests.test_shopify import FakeShopifyTransport


def _config() -> ShopifyConfig:
    return ShopifyConfig(
        store_domain="canada-vhs.myshopify.com",
        access_token="shpat_test_only",
        location_id="gid://shopify/Location/123",
        api_version="2026-07",
    )


def _make_ready(db_file: Path, item_id: str) -> None:
    db.update_item(
        db_file,
        item_id,
        {"title": f"Tape {item_id}", "price_cents": 1299, "condition": "Very Good", "ready": 1},
    )
    validate_items(db_file, [item_id])


def test_publish_queue_classifies_mixed_batch_and_survives_restart(tmp_path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    ready, blocked = [
        item["item_id"]
        for item in db.list_items(data_paths.db_file, batch_id_value=result.batch_id)
    ]
    _make_ready(data_paths.db_file, ready)

    with db.connect(data_paths.db_file) as connection:
        source = dict(
            connection.execute("SELECT * FROM items WHERE item_id=?", (ready,)).fetchone()
        )
        source_photos = [
            dict(row)
            for row in connection.execute("SELECT * FROM photos WHERE item_id=?", (ready,))
        ]
    for sequence, item_id, upload_status in (
        (3, "CVHS-MIXED-DRAFT", "UPLOADED"),
        (4, "CVHS-MIXED-FAIL", "FAILED"),
    ):
        clone = dict(source)
        clone.update(item_id=item_id, sku=item_id, sequence=sequence, upload_status=upload_status)
        if upload_status == "UPLOADED":
            clone.update(
                shopify_product_id="gid://shopify/Product/77",
                shopify_admin_url="https://canada-vhs.myshopify.com/admin/products/77",
            )
        else:
            clone.update(last_error="Temporary Shopify failure", retry_count=1)
        columns = list(clone)
        with db.transaction(data_paths.db_file) as connection:
            connection.execute(
                f"INSERT INTO items({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
                list(clone.values()),
            )
            connection.execute(
                "INSERT INTO shopify_sync(item_id, status) VALUES(?, ?)", (item_id, upload_status)
            )
            for offset, source_photo in enumerate(source_photos, start=1):
                photo = dict(source_photo)
                photo.pop("photo_id")
                photo.update(
                    item_id=item_id,
                    stream_index=sequence * 100 + offset,
                    proposed_name=f"{item_id}-{offset}.jpg",
                )
                photo_columns = list(photo)
                connection.execute(
                    f"INSERT INTO photos({','.join(photo_columns)}) VALUES({','.join('?' for _ in photo_columns)})",
                    list(photo.values()),
                )

    states = {
        entry.item_id: entry for entry in build_publish_queue(data_paths.db_file, result.batch_id)
    }
    assert states[ready].state == "Ready"
    assert states[blocked].state == "Blocked"
    assert states[blocked].reasons
    assert states["CVHS-MIXED-DRAFT"].state == "Drafted"
    assert states["CVHS-MIXED-DRAFT"].admin_url
    assert states["CVHS-MIXED-FAIL"].state == "Failed"
    assert "Temporary Shopify failure" in states["CVHS-MIXED-FAIL"].reasons
    assert {
        entry.item_id for entry in build_publish_queue(data_paths.db_file, result.batch_id)
    } == set(states)


class NoNetworkTransport:
    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("local simulation must not use the network transport")

    def upload(self, url: str, parameters: list[dict[str, str]], file_path: Path) -> None:
        raise AssertionError("local simulation must not upload")


def test_batch_simulation_is_local_and_invalid_items_never_reach_writes(
    tmp_path, data_paths
) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    ready, blocked = [
        item["item_id"]
        for item in db.list_items(data_paths.db_file, batch_id_value=result.batch_id)
    ]
    _make_ready(data_paths.db_file, ready)
    config = ShopifyConfig(store_domain="", access_token="", location_id="")
    service = ShopifyService(
        data_paths.db_file, config, ShopifyClient(config, NoNetworkTransport())
    )

    reports = simulate_selected(service, [ready, blocked])
    assert reports[0].ready is True
    assert reports[1].ready is False
    outcomes = create_selected_drafts(service, [blocked], confirmed=True)
    assert outcomes[0].outcome == "FAILED"
    assert "blocked upload" in outcomes[0].message


def test_batch_live_drafts_skip_completed_and_isolate_failures(tmp_path, data_paths) -> None:
    result = process_batch(create_demo_batch(tmp_path / "camera"), paths=data_paths)
    first, second = [
        item["item_id"]
        for item in db.list_items(data_paths.db_file, batch_id_value=result.batch_id)
    ]
    _make_ready(data_paths.db_file, first)
    _make_ready(data_paths.db_file, second)
    transport = FakeShopifyTransport()
    service = ShopifyService(data_paths.db_file, _config(), ShopifyClient(_config(), transport))

    first_run = create_selected_drafts(service, [first], confirmed=True)
    assert first_run[0].outcome == "DRAFTED"

    duplicate_transport = FakeShopifyTransport(duplicate_sku=True)
    duplicate_service = ShopifyService(
        data_paths.db_file, _config(), ShopifyClient(_config(), duplicate_transport)
    )
    outcomes = create_selected_drafts(duplicate_service, [second], confirmed=True)
    assert outcomes[0].outcome == "FAILED"
    assert duplicate_transport.operations == ["sku_check"]

    second_run = create_selected_drafts(service, [first, second], confirmed=True)
    assert [outcome.outcome for outcome in second_run] == ["SKIPPED_DRAFTED", "DRAFTED"]
    assert transport.operations.count("create_product") == 2
