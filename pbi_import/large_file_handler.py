"""
Large File Handler — enhanced import for .pbix files exceeding 1 GB.

Uses the PBI REST API ``/imports`` endpoint with ``CreateTemporaryUploadLocation``
for resumable, chunked uploads of large Power BI files.
"""

import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default chunk size: 4 MB (PBI API recommendation)
DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024


class LargeFileHandler:
    """Handle .pbix imports larger than 1 GB via chunked upload."""

    def __init__(self, pbi_client: Any, chunk_size: int = DEFAULT_CHUNK_SIZE):
        self.client = pbi_client
        self.chunk_size = chunk_size

    def upload(
        self,
        workspace_id: str,
        file_path: str,
        display_name: str | None = None,
        dry_run: bool = False,
    ) -> dict:
        """Upload a large .pbix file using chunked/resumable upload.

        Args:
            workspace_id: target workspace.
            file_path: path to the .pbix file.
            display_name: report display name (defaults to filename stem).
            dry_run: preview only.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        name = display_name or path.stem
        file_size = path.stat().st_size
        total_chunks = math.ceil(file_size / self.chunk_size)

        logger.info(
            "Large file upload: %s (%.1f MB, %d chunks)",
            name, file_size / (1024 * 1024), total_chunks,
        )

        if dry_run:
            logger.info("[DRY RUN] Would upload %s to workspace %s", name, workspace_id)
            return {"name": name, "status": "dry_run", "size_mb": file_size / (1024 * 1024)}

        # Step 1: Create temporary upload location
        upload_url = self.client.create_temporary_upload_location(workspace_id)
        logger.info("Temporary upload location created")

        # Step 2: Upload chunks
        with open(path, "rb") as f:
            for chunk_idx in range(total_chunks):
                chunk = f.read(self.chunk_size)
                offset = chunk_idx * self.chunk_size

                self.client.upload_chunk(
                    upload_url=upload_url,
                    chunk_data=chunk,
                    offset=offset,
                    total_size=file_size,
                )

                if (chunk_idx + 1) % 50 == 0 or chunk_idx == total_chunks - 1:
                    pct = ((chunk_idx + 1) / total_chunks) * 100
                    logger.info("Upload progress: %.0f%% (%d/%d)", pct, chunk_idx + 1, total_chunks)

        # Step 3: Complete the import
        result = self.client.complete_upload(
            workspace_id=workspace_id,
            upload_url=upload_url,
            display_name=name,
        )

        import_id = result.get("id", "")
        logger.info("Large file import initiated: %s (%s)", name, import_id)

        return {
            "name": name,
            "import_id": import_id,
            "size_mb": round(file_size / (1024 * 1024), 1),
            "chunks": total_chunks,
            "status": "imported",
        }

    @staticmethod
    def needs_chunked_upload(file_path: str, threshold_mb: int = 1024) -> bool:
        """Check if a file exceeds the threshold for chunked upload."""
        size = Path(file_path).stat().st_size
        return size > threshold_mb * 1024 * 1024
