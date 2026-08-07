from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Sequence

from ..models import CommandResult


@dataclass(slots=True)
class ProcessEvent:
    stream: str
    data: str


@dataclass(slots=True)
class AsyncProcessHandle:
    process: asyncio.subprocess.Process
    command: list[str]
    started_at: float
    output_limit: int
    stdout_chunks: list[str] = field(default_factory=list)
    stderr_chunks: list[str] = field(default_factory=list)
    output_bytes: int = 0
    cancelled: bool = False

    def _append(self, stream: str, text: str) -> None:
        encoded = text.encode("utf-8", errors="replace")
        self.output_bytes += len(encoded)
        if self.output_bytes > self.output_limit:
            raise RuntimeError(f"process output exceeded configured limit ({self.output_limit} bytes)")
        (self.stdout_chunks if stream == "stdout" else self.stderr_chunks).append(text)


class AsyncProcessSupervisor:
    """Bounded, cancellable subprocess supervisor for ADB-Gath 3.6.

    No shell is used. Output is bounded to protect the controller/Web UI from
    unbounded streams. On POSIX each process gets its own process group; on
    Windows CREATE_NEW_PROCESS_GROUP is used and descendants are terminated via
    taskkill only as a final cleanup mechanism.
    """

    def __init__(self, *, max_concurrency: int = 8, output_limit: int = 16 * 1024 * 1024) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        if output_limit < 4096:
            raise ValueError("output_limit is too small")
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self.output_limit = int(output_limit)

    async def start(
        self,
        command: Sequence[str],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> AsyncProcessHandle:
        if not command:
            raise ValueError("command is required")
        kwargs: dict[str, Any] = {
            "stdin": asyncio.subprocess.PIPE if stdin is not None else None,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "cwd": str(cwd) if cwd else None,
            "env": env,
        }
        if os.name == "nt":
            import subprocess

            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        process = await asyncio.create_subprocess_exec(*(str(x) for x in command), **kwargs)
        handle = AsyncProcessHandle(
            process=process,
            command=[str(x) for x in command],
            started_at=asyncio.get_running_loop().time(),
            output_limit=self.output_limit,
        )
        if stdin is not None and process.stdin is not None:
            process.stdin.write(stdin)
            await process.stdin.drain()
            process.stdin.close()
        return handle

    async def _terminate_tree(self, handle: AsyncProcessHandle, *, grace: float = 0.75) -> None:
        process = handle.process
        if process.returncode is not None:
            return
        handle.cancelled = True
        if os.name == "nt":
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                process.terminate()
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
            except Exception:
                process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=grace)
            return
        except asyncio.TimeoutError:
            pass
        if os.name == "nt":
            proc = await asyncio.create_subprocess_exec(
                "taskkill", "/PID", str(process.pid), "/T", "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        with contextlib.suppress(Exception):
            process.kill()
        await process.wait()

    async def stream(self, handle: AsyncProcessHandle) -> AsyncIterator[ProcessEvent]:
        queue: asyncio.Queue[ProcessEvent | None] = asyncio.Queue(maxsize=256)

        async def pump(name: str, reader: asyncio.StreamReader | None) -> None:
            if reader is None:
                await queue.put(None)
                return
            try:
                while True:
                    line = await reader.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace")
                    handle._append(name, text)
                    await queue.put(ProcessEvent(name, text))
            finally:
                await queue.put(None)

        tasks = [asyncio.create_task(pump("stdout", handle.process.stdout)), asyncio.create_task(pump("stderr", handle.process.stderr))]
        completed = 0
        try:
            while completed < len(tasks):
                event = await queue.get()
                if event is None:
                    completed += 1
                    continue
                yield event
        finally:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def run(
        self,
        command: Sequence[str],
        *,
        timeout: float = 60,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> CommandResult:
        async with self._semaphore:
            loop = asyncio.get_running_loop()
            handle = await self.start(command, cwd=cwd, env=env, stdin=stdin)
            try:
                await asyncio.wait_for(self._consume(handle), timeout=timeout)
            except asyncio.TimeoutError:
                await self._terminate_tree(handle)
                return CommandResult(
                    ok=False,
                    command=handle.command,
                    stdout="".join(handle.stdout_chunks),
                    stderr="Timed out.",
                    returncode=124,
                    duration_ms=int((loop.time() - handle.started_at) * 1000),
                    metadata={"timed_out": True},
                )
            except asyncio.CancelledError:
                await self._terminate_tree(handle)
                raise
            return CommandResult(
                ok=handle.process.returncode == 0 and not handle.cancelled,
                command=handle.command,
                stdout="".join(handle.stdout_chunks),
                stderr="".join(handle.stderr_chunks),
                returncode=handle.process.returncode or 0,
                duration_ms=int((loop.time() - handle.started_at) * 1000),
                metadata={"cancelled": handle.cancelled, "output_bytes": handle.output_bytes},
            )

    async def _consume(self, handle: AsyncProcessHandle) -> None:
        async for _ in self.stream(handle):
            pass
        await handle.process.wait()


# imported late to keep the main module namespace compact on Windows
import contextlib  # noqa: E402
