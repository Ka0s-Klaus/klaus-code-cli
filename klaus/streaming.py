"""StreamRenderer — spinner TTFT + live Markdown rendering durante streaming."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console
    from rich.live import Live


class StreamRenderer:
    """Gestiona la UX de streaming: spinner inicial (TTFT) y Markdown renderizado en vivo.

    Uso:
        renderer = StreamRenderer(console)
        renderer.start()
        response = await adapter.stream_message(..., on_token=renderer.on_token)
        full_text = renderer.stop()
    """

    def __init__(self, console: Console) -> None:
        self._console = console
        self._buf: list[str] = []
        self._live: Live | None = None

    def start(self) -> None:
        """Arranca el spinner de espera hasta el primer token (TTFT)."""
        from rich.live import Live
        from rich.spinner import Spinner

        self._live = Live(
            Spinner("dots", "[dim] Pensando...[/dim]"),
            console=self._console,
            refresh_per_second=12,
        )
        self._live.__enter__()

    def on_token(self, token: str) -> None:
        """Callback para cada token del stream — acumula y actualiza el render en vivo."""
        self._buf.append(token)
        if self._live is not None:
            from rich.markdown import Markdown

            self._live.update(Markdown("".join(self._buf)))

    def stop(self) -> str:
        """Finaliza el live render y devuelve el texto acumulado completo."""
        if self._live is not None:
            if not self._buf:
                from rich.text import Text

                self._live.update(Text(""))
            self._live.__exit__(None, None, None)
            self._live = None
        return "".join(self._buf)
