import asyncio
import logging

from binance_data_layer.collector import run_asyncio_entrypoint


def test_keyboard_interrupt_is_handled_without_reraising(monkeypatch, caplog):
    async def application():
        return None

    def interrupted_run(coro):
        coro.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(asyncio, "run", interrupted_run)
    with caplog.at_level(logging.INFO):
        run_asyncio_entrypoint(application)

    assert "Shutdown requested" in caplog.text
