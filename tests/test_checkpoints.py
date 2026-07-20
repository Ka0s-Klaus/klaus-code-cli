"""Tests para save_checkpoint, list_checkpoints y load_checkpoint en sessions.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def storage_path(tmp_path: Path) -> str:
    return str(tmp_path / "sessions")


SAMPLE_MESSAGES = [
    {"role": "user", "content": "Hola Klaus"},
    {"role": "assistant", "content": "¡Hola! ¿En qué puedo ayudarte?"},
    {"role": "user", "content": "Escribe un test de Python"},
]


class TestSaveCheckpoint:
    def test_creates_json_file(self, storage_path: str) -> None:
        from Klaus.sessions import save_checkpoint

        result = save_checkpoint(storage_path, "session-abc", SAMPLE_MESSAGES)

        assert "checkpoint_id" in result
        assert result["messages"] == len(SAMPLE_MESSAGES)
        assert Path(result["path"]).exists()

    def test_checkpoint_contains_messages(self, storage_path: str) -> None:
        from Klaus.sessions import save_checkpoint

        result = save_checkpoint(storage_path, "session-abc", SAMPLE_MESSAGES)
        data = json.loads(Path(result["path"]).read_text())

        assert data["messages"] == SAMPLE_MESSAGES
        assert data["session_id"] == "session-abc"

    def test_checkpoint_with_name(self, storage_path: str) -> None:
        from Klaus.sessions import save_checkpoint

        result = save_checkpoint(storage_path, "session-abc", SAMPLE_MESSAGES, name="pre-refactor")

        assert "pre-refactor" in result["checkpoint_id"]
        assert result["name"] == "pre-refactor"

    def test_checkpoint_without_name(self, storage_path: str) -> None:
        from Klaus.sessions import save_checkpoint

        result = save_checkpoint(storage_path, "session-abc", SAMPLE_MESSAGES)

        assert result["name"] == result["checkpoint_id"]

    def test_multiple_checkpoints_different_ids(self, storage_path: str) -> None:
        import time
        from Klaus.sessions import save_checkpoint

        cp1 = save_checkpoint(storage_path, "session-abc", SAMPLE_MESSAGES, name="v1")
        time.sleep(0.01)  # asegurar timestamp diferente
        cp2 = save_checkpoint(storage_path, "session-abc", SAMPLE_MESSAGES, name="v2")

        assert cp1["checkpoint_id"] != cp2["checkpoint_id"]


class TestListCheckpoints:
    def test_empty_session(self, storage_path: str) -> None:
        from Klaus.sessions import list_checkpoints

        result = list_checkpoints(storage_path, "session-nothing")
        assert result == []

    def test_lists_created_checkpoints(self, storage_path: str) -> None:
        import time
        from Klaus.sessions import list_checkpoints, save_checkpoint

        save_checkpoint(storage_path, "session-list", SAMPLE_MESSAGES, name="ckpt-a")
        time.sleep(0.01)
        save_checkpoint(storage_path, "session-list", SAMPLE_MESSAGES, name="ckpt-b")

        result = list_checkpoints(storage_path, "session-list")

        assert len(result) == 2

    def test_only_lists_session_checkpoints(self, storage_path: str) -> None:
        from Klaus.sessions import list_checkpoints, save_checkpoint

        save_checkpoint(storage_path, "session-X", SAMPLE_MESSAGES)
        save_checkpoint(storage_path, "session-Y", SAMPLE_MESSAGES)

        result_x = list_checkpoints(storage_path, "session-X")
        result_y = list_checkpoints(storage_path, "session-Y")

        assert len(result_x) == 1
        assert len(result_y) == 1

    def test_checkpoint_metadata(self, storage_path: str) -> None:
        from Klaus.sessions import list_checkpoints, save_checkpoint

        save_checkpoint(storage_path, "session-meta", SAMPLE_MESSAGES, name="meta-test")
        results = list_checkpoints(storage_path, "session-meta")

        assert len(results) == 1
        cp = results[0]
        assert "checkpoint_id" in cp
        assert "messages" in cp
        assert "timestamp" in cp
        assert cp["messages"] == len(SAMPLE_MESSAGES)


class TestLoadCheckpoint:
    def test_load_existing(self, storage_path: str) -> None:
        from Klaus.sessions import load_checkpoint, save_checkpoint

        saved = save_checkpoint(storage_path, "session-load", SAMPLE_MESSAGES, name="to-load")
        loaded = load_checkpoint(storage_path, saved["checkpoint_id"])

        assert loaded is not None
        assert loaded == SAMPLE_MESSAGES

    def test_load_nonexistent(self, storage_path: str) -> None:
        from Klaus.sessions import load_checkpoint

        result = load_checkpoint(storage_path, "nonexistent-checkpoint-id")
        assert result is None

    def test_roundtrip(self, storage_path: str) -> None:
        from Klaus.sessions import load_checkpoint, save_checkpoint

        original = [
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": [{"type": "text", "text": "respuesta"}]},
        ]
        saved = save_checkpoint(storage_path, "session-rt", original)
        loaded = load_checkpoint(storage_path, saved["checkpoint_id"])

        assert loaded == original
