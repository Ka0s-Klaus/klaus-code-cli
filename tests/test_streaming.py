"""Tests para klaus.streaming.StreamRenderer."""

from __future__ import annotations

import io

from rich.console import Console

from klaus.streaming import StreamRenderer


def make_renderer() -> StreamRenderer:
    return StreamRenderer(Console(file=io.StringIO(), force_terminal=False))


def test_stream_renderer_start_stop_no_tokens():
    renderer = make_renderer()
    renderer.start()
    result = renderer.stop()
    assert result == ""


def test_stream_renderer_accumulates_tokens():
    renderer = make_renderer()
    renderer.start()
    renderer.on_token("hola")
    renderer.on_token(" mundo")
    result = renderer.stop()
    assert result == "hola mundo"


def test_stream_renderer_stop_idempotent():
    renderer = make_renderer()
    renderer.start()
    renderer.stop()
    result = renderer.stop()
    assert result == ""


def test_stream_renderer_stop_without_start():
    renderer = make_renderer()
    result = renderer.stop()
    assert result == ""
