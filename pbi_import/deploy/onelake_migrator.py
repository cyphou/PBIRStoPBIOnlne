"""
OneLake Migrator — migrates files and data to OneLake storage.

Handles uploading exported content (PBIX, RDL, datasets) to OneLake
storage for Fabric workspace consumption.
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ONELAKE_DFS = "https://onelake.dfs.fabric.microsoft.com"
_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB


class OneLakeMigrator:
    """Migrate files to OneLake (Fabric's data lake)."""

    def __init__(self, client: Any):
        self.client = client
        self.base_url = _ONELAKE_DFS

    def upload_file(
        self,
        workspace_id: str,
        item_id: str,
        local_path: str,
        remote_path: str,
        dry_run: bool = False,
    ) -> dict:
        """Upload a single file to OneLake.

        Args:
            workspace_id: Fabric workspace ID.
            item_id: Fabric item (lakehouse/warehouse) ID.
            local_path: local file path.
            remote_path: destination path within OneLake.
            dry_run: preview only.
        """
        file = Path(local_path)
        if not file.exists():
            logger.error("File not found: %s", local_path)
            return {"status": "error", "error": "File not found"}

        size = file.stat().st_size
        checksum = self._file_hash(file)

        if dry_run:
            logger.info(
                "[DRY RUN] Would upload %s (%d bytes) to %s",
                file.name, size, remote_path,
            )
            return {
                "file": file.name,
                "size": size,
                "checksum": checksum,
                "status": "dry_run",
            }

        url = (
            f"{self.base_url}/{workspace_id}/{item_id}/Files/{remote_path}"
        )

        if size <= _CHUNK_SIZE:
            # Single PUT
            with open(file, "rb") as f:
                self.client.put(url, data=f.read(), params={"resource": "file"})
        else:
            # Chunked upload
            self._chunked_upload(url, file, size)

        logger.info("Uploaded %s (%d bytes) → %s", file.name, size, remote_path)
        return {
            "file": file.name,
            "size": size,
            "checksum": checksum,
            "remote_path": remote_path,
            "status": "uploaded",
        }

    def upload_directory(
        self,
        workspace_id: str,
        item_id: str,
        local_dir: str,
        remote_prefix: str = "",
        dry_run: bool = False,
    ) -> list[dict]:
        """Upload all files in a directory to OneLake."""
        results: list[dict] = []
        source = Path(local_dir)

        if not source.is_dir():
            logger.error("Directory not found: %s", local_dir)
            return results

        for file in sorted(source.rglob("*")):
            if file.is_dir():
                continue

            relative = file.relative_to(source).as_posix()
            remote_path = f"{remote_prefix}/{relative}" if remote_prefix else relative

            result = self.upload_file(
                workspace_id=workspace_id,
                item_id=item_id,
                local_path=str(file),
                remote_path=remote_path,
                dry_run=dry_run,
            )
            results.append(result)

            if not dry_run:
                time.sleep(0.2)

        logger.info("Uploaded %d files from %s", len(results), local_dir)
        return results

    def save_manifest(self, output_dir: str, results: list[dict]) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "onelake_upload_manifest.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        return path

    def _chunked_upload(self, url: str, file: Path, size: int) -> None:
        """Upload a file in chunks."""
        # Create file resource
        self.client.put(url, params={"resource": "file"})

        offset = 0
        with open(file, "rb") as f:
            while offset < size:
                chunk = f.read(_CHUNK_SIZE)
                chunk_len = len(chunk)
                self.client.patch(
                    url,
                    data=chunk,
                    params={
                        "action": "append",
                        "position": str(offset),
                    },
                    headers={"Content-Length": str(chunk_len)},
                )
                offset += chunk_len

        # Flush
        self.client.patch(
            url, params={"action": "flush", "position": str(size)},
        )

    @staticmethod
    def _file_hash(path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
