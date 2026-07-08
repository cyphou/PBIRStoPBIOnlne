"""Tests for PaginatedPublisher ordering and retry behavior."""

from pathlib import Path
from unittest.mock import MagicMock

from pbi_import.paginated_publisher import PaginatedPublisher


def _write_rdl(path: Path, name: str) -> None:
    path.write_text(f"<Report Name=\"{name}\" />", encoding="utf-8")


def test_publish_all_applies_preferred_order(tmp_path):
    paginated_dir = tmp_path / "paginated"
    paginated_dir.mkdir()
    _write_rdl(paginated_dir / "B.rdl", "B")
    _write_rdl(paginated_dir / "A.rdl", "A")

    call_order: list[str] = []

    client = MagicMock()

    def _import_rdl(*, workspace_id, display_name, file_content):  # noqa: ARG001
        call_order.append(display_name)
        return {"id": f"id-{display_name}"}

    client.import_rdl.side_effect = _import_rdl

    publisher = PaginatedPublisher(client)
    result = publisher.publish_all(
        str(tmp_path),
        "ws-1",
        preferred_order=["/Reports/B", "/Reports/A"],
    )

    assert len(result["success"]) == 2
    assert result["failed"] == []
    assert call_order == ["B", "A"]


def test_publish_all_retries_failed_items(tmp_path):
    paginated_dir = tmp_path / "paginated"
    paginated_dir.mkdir()
    _write_rdl(paginated_dir / "A.rdl", "A")
    _write_rdl(paginated_dir / "B.rdl", "B")

    attempts: dict[str, int] = {"A": 0, "B": 0}

    client = MagicMock()

    def _import_rdl(*, workspace_id, display_name, file_content):  # noqa: ARG001
        attempts[display_name] += 1
        if display_name == "A" and attempts[display_name] == 1:
            raise RuntimeError("Dependency not found")
        return {"id": f"id-{display_name}"}

    client.import_rdl.side_effect = _import_rdl

    publisher = PaginatedPublisher(client)
    result = publisher.publish_all(
        str(tmp_path),
        "ws-1",
        preferred_order=["/Reports/A", "/Reports/B"],
        retry_failed_passes=1,
    )

    assert len(result["success"]) == 2
    assert result["failed"] == []
    assert attempts["A"] == 2
    assert attempts["B"] == 1
