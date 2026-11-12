"""
Invoice Detective AI — File Handling Utilities.

Validation, hashing, safe naming, and deletion of uploaded files.
"""

import hashlib
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import UploadFile, HTTPException


# Allowed file extensions and their expected MIME types
ALLOWED_EXTENSIONS = {
    ".pdf": ["application/pdf"],
    ".jpg": ["image/jpeg"],
    ".jpeg": ["image/jpeg"],
    ".png": ["image/png"],
}

# Magic byte signatures for file type validation
FILE_SIGNATURES = {
    ".pdf": b"%PDF",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png": b"\x89PNG",
}


async def validate_file(
    file: UploadFile, max_size_bytes: int
) -> tuple[str, bytes]:
    """
    Validate an uploaded file's extension, MIME type, signature, and size.

    Returns:
        Tuple of (extension, file_bytes).

    Raises:
        HTTPException: If any validation fails.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    # Check extension
    original_name = file.filename.lower()
    ext = os.path.splitext(original_name)[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' is not allowed. Accepted: {', '.join(ALLOWED_EXTENSIONS.keys())}",
        )

    # Check MIME type
    content_type = file.content_type or ""
    expected_mimes = ALLOWED_EXTENSIONS[ext]
    if content_type not in expected_mimes:
        raise HTTPException(
            status_code=400,
            detail=f"MIME type '{content_type}' does not match expected type for '{ext}'.",
        )

    # Read at most one byte past the limit so oversized uploads don't consume unbounded memory.
    file_bytes = await file.read(max_size_bytes + 1)

    # Check size
    if len(file_bytes) > max_size_bytes:
        max_mb = max_size_bytes / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds the maximum allowed size of {max_mb:.0f} MB.",
        )

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Check file signature (magic bytes)
    if not check_file_signature(file_bytes, ext):
        raise HTTPException(
            status_code=400,
            detail="File content does not match its declared type. Possible corrupt or misnamed file.",
        )

    return ext, file_bytes


def check_file_signature(file_bytes: bytes, ext: str) -> bool:
    """Verify file magic bytes match the expected signature for the extension."""
    expected = FILE_SIGNATURES.get(ext)
    if expected is None:
        return True  # No signature check available
    return file_bytes[: len(expected)] == expected


def compute_file_hash(file_bytes: bytes) -> str:
    """Compute SHA-256 hash of file content."""
    return hashlib.sha256(file_bytes).hexdigest()


def generate_safe_filename(original_name: str) -> str:
    """Generate a safe stored filename: uuid4 + original extension."""
    ext = os.path.splitext(original_name)[1].lower()
    return f"{uuid.uuid4().hex}{ext}"


def delete_stored_file(stored_filename: str, upload_dir: str) -> bool:
    """
    Safely delete a stored file.

    Returns True if deleted, False if file did not exist.
    Raises HTTPException on path traversal attempts.
    """
    # Resolve paths to prevent traversal
    upload_path = Path(upload_dir).resolve()
    file_path = (upload_path / stored_filename).resolve()

    # Validate the file is within the upload directory
    if file_path == upload_path or file_path.parent != upload_path:
        raise HTTPException(
            status_code=400, detail="Invalid file path detected."
        )

    if file_path.exists():
        file_path.unlink()
        return True
    return False


def get_safe_file_path(stored_filename: str, upload_dir: str) -> Optional[Path]:
    """
    Get the resolved file path after validating against traversal.

    Returns None if the file doesn't exist or path is invalid.
    """
    upload_path = Path(upload_dir).resolve()
    file_path = (upload_path / stored_filename).resolve()

    # Validate the file is within the upload directory
    if file_path == upload_path or file_path.parent != upload_path:
        return None

    if not file_path.exists():
        return None

    return file_path
