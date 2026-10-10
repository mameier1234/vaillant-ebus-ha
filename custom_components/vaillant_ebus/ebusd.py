"""Minimaler async-Client fuer den ebusd-TCP-Kommandoport (Standard 8888)."""

from __future__ import annotations

import asyncio
import re

CONNECT_TIMEOUT = 5
COMMAND_TIMEOUT = 20

_SAFE = re.compile(r"^[A-Za-z0-9_.:;\- ]+$")


class EbusdError(Exception):
    """ebusd hat einen Fehler gemeldet oder ist nicht erreichbar."""


class EbusdClient:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._lock = asyncio.Lock()  # ein Kommando nach dem anderen

    async def command(self, cmd: str) -> str:
        if not _SAFE.match(cmd):
            raise EbusdError(f"Unzulaessige Zeichen im Kommando: {cmd!r}")
        async with self._lock:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self._host, self._port), CONNECT_TIMEOUT
                )
            except (OSError, asyncio.TimeoutError) as err:
                raise EbusdError(f"ebusd nicht erreichbar: {err}") from err
            try:
                writer.write(f"{cmd}\n".encode())
                await writer.drain()
                raw = await asyncio.wait_for(reader.readuntil(b"\n\n"), COMMAND_TIMEOUT)
            except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as err:
                raise EbusdError(f"Kommunikationsfehler bei {cmd!r}: {err}") from err
            finally:
                writer.close()
        text = raw.decode(errors="replace").strip()
        if text.startswith("ERR"):
            raise EbusdError(f"{cmd!r}: {text}")
        return text

    async def read(self, circuit: str, name: str, *, fresh: bool = False, max_age: int = 60) -> list[str]:
        flag = "-f" if fresh else f"-m {max_age}"
        return (await self.command(f"read {flag} -c {circuit} {name}")).split(";")

    async def write(self, circuit: str, name: str, value: str) -> None:
        result = await self.command(f"write -c {circuit} {name} {value}")
        if result != "done":
            raise EbusdError(f"Unerwartete Antwort auf write {circuit} {name}: {result!r}")
