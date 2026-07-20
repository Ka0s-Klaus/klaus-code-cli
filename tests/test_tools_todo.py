"""Tests para Klaus.tools.todo — todo_write y todo_read."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def reset_todos():
    """Limpia el estado global de todos antes y después de cada test."""
    from Klaus.tools.todo import _set_todos
    _set_todos([])
    yield
    _set_todos([])


class TestTodoWrite:
    @pytest.mark.asyncio
    async def test_write_creates_todos(self) -> None:
        from Klaus.tools.todo import todo_write

        todos = [
            {"content": "Implementar feature X", "status": "pending"},
            {"content": "Revisar PR", "status": "in_progress"},
        ]
        result = await todo_write(todos=todos)

        assert result["status"] == "ok"
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_write_replaces_existing(self) -> None:
        from Klaus.tools.todo import todo_read, todo_write

        await todo_write(todos=[{"content": "Primera tarea", "status": "pending"}])
        await todo_write(todos=[
            {"content": "Nueva tarea A", "status": "pending"},
            {"content": "Nueva tarea B", "status": "completed"},
        ])

        result = await todo_read()
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_write_normalizes_invalid_status(self) -> None:
        from Klaus.tools.todo import todo_read, todo_write

        await todo_write(todos=[{"content": "Tarea", "status": "invalid_status"}])
        result = await todo_read()
        assert result["todos"][0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_write_filters_empty_content(self) -> None:
        from Klaus.tools.todo import todo_read, todo_write

        await todo_write(todos=[
            {"content": "   ", "status": "pending"},
            {"content": "Tarea válida", "status": "pending"},
        ])
        result = await todo_read()
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_write_empty_list(self) -> None:
        from Klaus.tools.todo import todo_write

        result = await todo_write(todos=[])
        assert result["count"] == 0


class TestTodoRead:
    @pytest.mark.asyncio
    async def test_read_initial_empty(self) -> None:
        from Klaus.tools.todo import todo_read

        result = await todo_read()
        assert result["count"] == 0
        assert result["todos"] == []

    @pytest.mark.asyncio
    async def test_read_counts_by_status(self) -> None:
        from Klaus.tools.todo import todo_read, todo_write

        await todo_write(todos=[
            {"content": "A", "status": "pending"},
            {"content": "B", "status": "pending"},
            {"content": "C", "status": "in_progress"},
            {"content": "D", "status": "completed"},
        ])

        result = await todo_read()
        assert result["pending"] == 2
        assert result["in_progress"] == 1
        assert result["completed"] == 1

    @pytest.mark.asyncio
    async def test_get_todos_for_display(self) -> None:
        from Klaus.tools.todo import get_todos_for_display, todo_write

        await todo_write(todos=[{"content": "Test", "status": "pending"}])
        todos = get_todos_for_display()
        assert len(todos) == 1
        assert todos[0]["content"] == "Test"
