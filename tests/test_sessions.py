"""Tests para klaus.sessions — SessionManager y SessionLock."""

from __future__ import annotations

import pytest

from klaus.sessions import (
    SessionLock,
    SessionManager,
    clear_all_sessions,
    delete_session,
    get_session,
    list_sessions,
)


@pytest.fixture
def storage(tmp_path):
    return str(tmp_path / "sessions")


@pytest.fixture
def project(tmp_path):
    return tmp_path / "project"


def test_session_manager_load_empty(storage, project):
    mgr = SessionManager(storage, project)
    assert mgr.load() == []


def test_session_manager_save_and_load(storage, project):
    mgr = SessionManager(storage, project)
    msgs = [{"role": "user", "content": "hola"}]
    mgr.save(msgs)
    assert mgr.load() == msgs


def test_session_manager_clear(storage, project):
    mgr = SessionManager(storage, project)
    mgr.save([{"role": "user", "content": "x"}])
    mgr.clear()
    assert mgr.load() == []


def test_session_manager_named_session(tmp_path):
    s = str(tmp_path / "s")
    mgr = SessionManager(s, tmp_path, session_name="mysession")
    assert mgr.session_id == "mysession"
    mgr.save([{"role": "user", "content": "data"}])
    mgr2 = SessionManager(s, tmp_path, session_name="mysession")
    assert mgr2.load() == [{"role": "user", "content": "data"}]


def test_list_sessions_empty(storage):
    assert list_sessions(storage) == []


def test_list_sessions_after_save(storage, project):
    mgr = SessionManager(storage, project)
    mgr.save([{"role": "user", "content": "x"}])
    sessions = list_sessions(storage)
    assert len(sessions) == 1
    assert sessions[0]["messages"] == 1


def test_session_lock_disabled(storage, project):
    lock = SessionLock(storage, project, enabled=False)
    assert lock.acquire() is True
    lock.release()


def test_session_lock_acquire_and_release(storage, project):
    lock = SessionLock(storage, project, enabled=True)
    assert lock.acquire() is True
    lock.release()
    assert lock.acquire() is True
    lock.release()


def test_get_and_delete_session(storage, project):
    mgr = SessionManager(storage, project)
    msgs = [{"role": "user", "content": "test"}]
    mgr.save(msgs)
    sid = mgr.session_id
    assert get_session(storage, sid) == msgs
    assert delete_session(storage, sid) is True
    assert get_session(storage, sid) is None


def test_clear_all_sessions(tmp_path):
    s = str(tmp_path / "s")
    for i in range(3):
        mgr = SessionManager(s, tmp_path / f"p{i}", session_name=f"sess{i}")
        mgr.save([{"role": "user", "content": f"msg{i}"}])
    assert clear_all_sessions(s) == 3
