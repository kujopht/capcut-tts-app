"""Unit tests for cover_resolver.py production novel_id safety and rollback.

Tests:
1. New novel cover approval.
2. Existing novel replacement requires confirm_replace.
3. Explicit confirm_replace creates rollback backup.
4. Rollback successfully restores previous cover.
5. Wrong/nonexistent ID fails without Appwrite mutation.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from scripts.content_factory import cover_resolver


@pytest.fixture
def mock_cover_workspace(tmp_path, monkeypatch):
    """Sets up disposable staged and approved cover directories."""
    staged = tmp_path / "staged"
    approved = tmp_path / "approved"
    monkeypatch.setattr(cover_resolver, "STAGED_COVERS_DIR", staged)
    monkeypatch.setattr(cover_resolver, "APPROVED_COVERS_DIR", approved)
    staged.mkdir(parents=True, exist_ok=True)
    approved.mkdir(parents=True, exist_ok=True)
    return {"staged": staged, "approved": approved}


def test_new_novel_cover_approval(mock_cover_workspace):
    """New cover stages and approves cleanly."""
    work_id = "test_work_001"
    staged_work = mock_cover_workspace["staged"] / work_id
    staged_work.mkdir(parents=True)
    (staged_work / "active_staged.jpg").write_bytes(b"FAKE_STAGED_IMAGE_BYTES_1")
    (staged_work / "metadata.json").write_text(json.dumps({
        "work_id": work_id,
        "status": "pending_review",
        "provider": "beam_animagine",
    }), encoding="utf-8")

    success, msg, meta = cover_resolver.approve_cover(work_id=work_id, novel_id="nov_rr_test_work_001")
    assert success is True
    assert "approved successfully" in msg.lower()
    assert (mock_cover_workspace["approved"] / work_id / "cover.jpg").exists()
    assert (mock_cover_workspace["approved"] / work_id / "cover.jpg").read_bytes() == b"FAKE_STAGED_IMAGE_BYTES_1"


def test_existing_novel_replacement_requires_confirmation(mock_cover_workspace):
    """Replacing an existing cover without confirm_replace must fail."""
    work_id = "test_work_002"
    # Setup already approved cover
    appr_dir = mock_cover_workspace["approved"] / work_id
    appr_dir.mkdir(parents=True)
    (appr_dir / "cover.jpg").write_bytes(b"OLD_APPROVED_IMAGE")

    # Setup new staged cover
    staged_work = mock_cover_workspace["staged"] / work_id
    staged_work.mkdir(parents=True)
    (staged_work / "active_staged.jpg").write_bytes(b"NEW_CANDIDATE_IMAGE")
    (staged_work / "metadata.json").write_text(json.dumps({
        "work_id": work_id,
        "status": "pending_review",
    }), encoding="utf-8")

    # Attempt approve without confirm_replace
    success, msg, _ = cover_resolver.approve_cover(work_id=work_id, confirm_replace=False)
    assert success is False
    assert "confirmation required" in msg.lower()
    # Ensure old image was NOT replaced
    assert (appr_dir / "cover.jpg").read_bytes() == b"OLD_APPROVED_IMAGE"


def test_explicit_confirm_replace_and_rollback(mock_cover_workspace):
    """Explicit confirm_replace replaces cover, saves backup, and allows rollback."""
    work_id = "test_work_003"
    appr_dir = mock_cover_workspace["approved"] / work_id
    appr_dir.mkdir(parents=True)
    (appr_dir / "cover.jpg").write_bytes(b"ORIGINAL_COVER_BYTES")

    staged_work = mock_cover_workspace["staged"] / work_id
    staged_work.mkdir(parents=True)
    (staged_work / "active_staged.jpg").write_bytes(b"NEW_REPLACEMENT_BYTES")
    (staged_work / "metadata.json").write_text(json.dumps({
        "work_id": work_id,
        "status": "pending_review",
    }), encoding="utf-8")

    # Approve with confirm_replace=True
    success, msg, meta = cover_resolver.approve_cover(work_id=work_id, confirm_replace=True)
    assert success is True
    assert (appr_dir / "cover.jpg").read_bytes() == b"NEW_REPLACEMENT_BYTES"
    assert "previous_cover" in meta
    backup_file = Path(meta["previous_cover"]["backup_file"])
    assert backup_file.exists()
    assert backup_file.read_bytes() == b"ORIGINAL_COVER_BYTES"

    # Now test rollback
    rb_success, rb_msg, rb_meta = cover_resolver.rollback_cover(work_id=work_id)
    assert rb_success is True
    assert "rolled back" in rb_msg.lower()
    # Verified restored bytes
    assert (appr_dir / "cover.jpg").read_bytes() == b"ORIGINAL_COVER_BYTES"


def test_nonexistent_id_fails_without_mutation(mock_cover_workspace):
    """Nonexistent Appwrite novel ID fails closed without mutation."""
    work_id = "test_work_004"
    staged_work = mock_cover_workspace["staged"] / work_id
    staged_work.mkdir(parents=True)
    (staged_work / "active_staged.jpg").write_bytes(b"VALID_STAGED_BYTES")
    (staged_work / "metadata.json").write_text(json.dumps({
        "work_id": work_id,
        "status": "pending_review",
    }), encoding="utf-8")

    mock_resp_404 = MagicMock()
    mock_resp_404.status_code = 404

    with patch("dotenv.dotenv_values", return_value={
        "R2_ACCOUNT_ID": "mock_r2", "R2_ACCESS_KEY_ID": "k", "R2_SECRET_ACCESS_KEY": "s",
        "APPWRITE_ENDPOINT": "https://cloud.appwrite.io/v1", "APPWRITE_PROJECT_ID": "p",
        "APPWRITE_API_KEY": "k", "APPWRITE_DATABASE_ID": "db",
    }), patch("boto3.client") as mock_boto, patch("requests.get", return_value=mock_resp_404) as mock_get, patch("requests.patch") as mock_patch:

        success, msg, _ = cover_resolver.approve_cover(
            work_id=work_id,
            novel_id="nov_nonexistent_9999",
            upload_r2=True,
            update_appwrite=True,
        )

        assert success is False
        assert "not found in appwrite (404)" in msg.lower()
        # Crucial: PATCH must NEVER be called if GET returned 404
        mock_patch.assert_not_called()
