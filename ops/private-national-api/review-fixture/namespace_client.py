"""Fixed namespace HTTP client; closed protocol, no Docker or arbitrary targets."""

import http.client
import ipaddress
import json
import math
import os
import re
import select
import signal
import socket
import sys
import time
from contextlib import contextmanager
from pathlib import Path

PORT = 8081
BODY = json.dumps(
    {
        "origins": [[41.90, -87.66], [42.06, -87.88]],
        "objective": "maximum",
        "holes": [9, 18],
    }
).encode()
MAX_LINE = 4096
MAX_BYTES = 65536
MAX_COMMANDS = 64
CONNECT_SECONDS = 2


@contextmanager
def absolute_watchdog(deadline):
    """Linux main-process alarm, independent of Docker and the API under test."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("absolute controller/request deadline")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()

    def expire(signum, frame):
        raise TimeoutError("absolute controller/request deadline")

    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(
        signal.ITIMER_REAL,
        min(remaining, previous_timer[0]) if previous_timer[0] else remaining,
    )
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            restored = previous_timer[0] - (time.monotonic() - started)
            if restored <= 0:
                raise TimeoutError("enclosing absolute deadline expired")
            signal.setitimer(signal.ITIMER_REAL, restored, previous_timer[1])


def remaining_seconds(deadline, ceiling):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("absolute controller/request deadline")
    return min(remaining, ceiling)


class ReviewHTTPResponse(http.client.HTTPResponse):
    """Stdlib framing with strict chunk terminators and bounded trailers."""

    # Same protocol guard as the native review's smoke parser; no native
    # cancellation or engine-evidence logic is imported into this controller.
    def _get_chunk_left(self):
        if self.chunk_left == 0:
            if self._safe_read(2) != b"\r\n":
                raise http.client.IncompleteRead(b"")
            self.chunk_left = None
        return super()._get_chunk_left()

    def _read_and_discard_trailer(self):
        for _ in range(32):
            line = self.fp.readline(8193)
            if line == b"\r\n":
                return
            if not line or not line.endswith(b"\r\n"):
                raise http.client.IncompleteRead(b"")
            if len(line) > 8192:
                raise http.client.HTTPException("review trailer line exceeds bound")
        raise http.client.HTTPException("review trailer count exceeds bound")


def read_response(client, end):
    response = None
    try:
        transport = client.sock
        transport.settimeout(remaining_seconds(end, 35))
        client.response_class = ReviewHTTPResponse
        response = client.getresponse()
        raw = bytearray()
        while not response.isclosed():
            transport.settimeout(remaining_seconds(end, 35))
            chunk = response.read1(min(65536, 1048577 - len(raw)))
            remaining_seconds(end, 35)
            if not chunk:
                break
            raw.extend(chunk)
            assert len(raw) <= 1048576, "response body exceeds 1 MiB"
        remaining_seconds(end, 35)
        if response.length not in (None, 0):
            raise http.client.IncompleteRead(bytes(raw), response.length)
        if response.chunked and not response.isclosed():
            raise http.client.IncompleteRead(bytes(raw))
        body = json.loads(raw.decode("utf-8"))
        remaining_seconds(end, 35)
        return response.status, body, response.getheader("Retry-After")
    finally:
        if response is not None:
            response.close()


def request(path="/health", body=None, timeout=35, *, deadline=None, host="127.0.0.1"):
    end = time.monotonic() + timeout
    if deadline is not None:
        end = min(end, deadline)
    remaining = remaining_seconds(end, min(timeout, CONNECT_SECONDS))
    with absolute_watchdog(end):
        client = http.client.HTTPConnection(host, PORT, timeout=remaining)
        try:
            send_end = min(end, time.monotonic() + CONNECT_SECONDS)
            with absolute_watchdog(send_end):
                client.request(
                    "GET" if body is None else "POST",
                    path,
                    body=body,
                    headers={}
                    if body is None
                    else {"Content-Type": "application/json"},
                )
                remaining_seconds(send_end, CONNECT_SECONDS)
            return read_response(client, end)
        finally:
            client.close()


def response_result(status, retry):
    """Only bounded ASCII retry seconds may cross the stdio boundary."""
    if retry is not None and (
        not isinstance(retry, str) or re.fullmatch(r"[0-9]{1,4}", retry) is None
    ):
        raise ValueError("invalid retry header")
    return {"outcome": "response", "status": status, "retry_after": retry}


class ProtocolEmitter:
    """Bound encoded bytes before writing; a rejected output is terminal."""

    def __init__(self, session, fd=None):
        self.session = session
        self.fd = sys.stdout.fileno() if fd is None else fd
        os.set_blocking(self.fd, False)
        self.total = 0
        self.failed = False

    def emit(self, event, sequence, *, deadline, **fields):
        if self.failed:
            raise ValueError("protocol output already failed")
        raw = (
            json.dumps(
                {"event": event, "session": self.session, "seq": sequence, **fields}
            )
            + "\n"
        ).encode("utf-8")
        if len(raw) > MAX_LINE or self.total + len(raw) > MAX_BYTES:
            self.failed = True
            raise ValueError("protocol output budget")
        self.total += len(raw)  # Never refund an uncertain/partial write.
        cursor = 0
        try:
            while cursor < len(raw):
                if select.select([], [self.fd], [], remaining_seconds(deadline, 0.1))[
                    1
                ]:
                    try:
                        written = os.write(self.fd, raw[cursor:])
                    except BlockingIOError:
                        continue
                    if not written:
                        raise OSError("protocol write made no progress")
                    cursor += written
            remaining_seconds(deadline, 0.1)
        except (Exception, KeyboardInterrupt, SystemExit):
            self.failed = True
            raise


class NamespaceClient:
    def __init__(self, peer, deadline):
        address = ipaddress.IPv4Address(peer)
        if not address.is_private or address.is_unspecified or address.is_multicast:
            raise ValueError("invalid fixed peer")
        self.peer = str(address)
        self.deadline = deadline
        self.pending = {}
        self.idle = []
        self.idle_deadline = None
        self.idle_used = False
        self.attempts = 0
        self.last_attempt = 0

    def end(self):
        return min(
            [
                self.deadline,
                *[end for _, end in self.pending.values()],
                *([self.idle_deadline] if self.idle else []),
            ]
        )

    def allocate(self, command):
        attempt = command["attempt"]
        if (
            type(attempt) is not int
            or not self.last_attempt < attempt <= 48
            or self.attempts >= 12
        ):
            raise ValueError("request budget or identity")
        self.last_attempt = attempt
        self.attempts += 1
        return attempt

    def connection(self, seconds):
        return http.client.HTTPConnection(
            self.peer, PORT, timeout=remaining_seconds(self.end(), seconds)
        )

    def handle(self, command):
        remaining_seconds(self.end(), 1)
        op = command["op"]
        expected = {
            "health": {"seq", "op", "attempt"},
            "ranking": {"seq", "op", "attempt"},
            "begin": {"seq", "op", "attempt"},
            "collect": {"seq", "op", "attempt"},
            "close": {"seq", "op", "attempt"},
            "idle-open": {"seq", "op"},
            "idle-close": {"seq", "op"},
            "finish": {"seq", "op"},
        }
        if op not in expected or set(command) != expected[op]:
            raise ValueError("closed command schema")
        if op in {"health", "ranking"}:
            self.allocate(command)
            if len(self.pending) >= 2:
                raise ValueError("outstanding request budget")
            try:
                status, _, retry = request(
                    "/health" if op == "health" else "/api/national/rankings",
                    None if op == "health" else BODY,
                    timeout=1 if op == "health" else 35,
                    deadline=self.end(),
                    host=self.peer,
                )
                return response_result(status, retry)
            except (OSError, http.client.HTTPException, ValueError) as error:
                return {
                    "outcome": "transport-error",
                    "exception_type": type(error).__name__,
                }
        if op == "begin":
            attempt = self.allocate(command)
            if len(self.pending) >= 2:
                raise ValueError("outstanding request budget")
            connection = self.connection(CONNECT_SECONDS)
            end = min(self.end(), time.monotonic() + 35)
            try:
                with absolute_watchdog(min(end, time.monotonic() + CONNECT_SECONDS)):
                    connection.request(
                        "POST",
                        "/api/national/rankings",
                        BODY,
                        {"Content-Type": "application/json"},
                    )
                self.pending[attempt] = (connection, end)
            except BaseException:
                connection.close()
                raise
            return {"outcome": "begun", "attempt": attempt}
        if op in {"collect", "close"}:
            attempt = command["attempt"]
            if type(attempt) is not int or attempt not in self.pending:
                raise ValueError("unknown pending attempt")
            connection, end = self.pending[attempt]
            if op == "close":
                connection.close()
                del self.pending[attempt]
                return {"outcome": "closed", "attempt": attempt}
            try:
                with absolute_watchdog(min(end, self.end())):
                    status, _, retry = read_response(connection, min(end, self.end()))
                return response_result(status, retry)
            except (OSError, http.client.HTTPException, ValueError) as error:
                return {
                    "outcome": "transport-error",
                    "exception_type": type(error).__name__,
                }
            finally:
                connection.close()
                del self.pending[attempt]
        if op == "idle-open":
            if self.idle_used:
                raise ValueError("idle socket budget")
            self.idle_used = True
            self.idle_deadline = min(self.end(), time.monotonic() + 35)
            try:
                for _ in range(8):
                    with absolute_watchdog(self.end()):
                        sock = socket.create_connection(
                            (self.peer, PORT), timeout=remaining_seconds(self.end(), 1)
                        )
                        self.idle.append(sock)
                        sock.sendall(b"GET /health HTTP/1.1\r\n")
                time.sleep(0.2)
            except BaseException:
                self.close_all()
                raise
            return {"outcome": "idle-open", "count": 8}
        if op == "idle-close":
            for sock in self.idle:
                sock.close()
            self.idle.clear()
            return {"outcome": "idle-closed"}
        if self.pending or self.idle:
            raise ValueError("unfinished sockets")
        return {"outcome": "finished"}

    def close_all(self):
        for connection, _ in self.pending.values():
            try:
                connection.close()
            except OSError:
                pass
        self.pending.clear()
        for sock in self.idle:
            try:
                sock.close()
            except OSError:
                pass
        self.idle.clear()


def isolation_facts():
    status = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    return {
        "uid": os.getuid(),
        "cap_eff": status["CapEff"].strip(),
        "no_new_privs": status["NoNewPrivs"].strip(),
        "seccomp": status["Seccomp"].strip(),
        "limits": {
            name: Path("/sys/fs/cgroup", name).read_text().strip()
            for name in ("memory.max", "cpu.max", "pids.max")
        },
    }


def main():
    if len(sys.argv) != 4 or not re.fullmatch(r"[a-f0-9]{32}", sys.argv[2]):
        raise ValueError("fixed namespace arguments")
    duration = float(sys.argv[3])
    if not math.isfinite(duration) or not 0 < duration <= 90:
        raise ValueError("session duration bound")
    session = sys.argv[2]
    client = NamespaceClient(sys.argv[1], time.monotonic() + duration)
    sequence = 0
    command_deadline = client.end()
    emitter = ProtocolEmitter(session)

    def emit(event, **fields):
        emitter.emit(
            event, sequence, deadline=min(command_deadline, client.end()), **fields
        )

    buffer = bytearray()
    total = 0
    try:
        emit(
            "ready",
            pid=os.getpid(),
            start_ticks=Path("/proc/self/stat")
            .read_text()
            .rsplit(")", 1)[1]
            .split()[19],
            peer=client.peer,
            port=PORT,
            isolation=isolation_facts(),
        )
        os.set_blocking(sys.stdin.fileno(), False)
        while sequence < MAX_COMMANDS:
            end = client.end()
            command_deadline = (
                end  # Retain the budget even if handling removes sockets.
            )
            remaining_seconds(end, 1)
            if not select.select(
                [sys.stdin], [], [], min(0.1, remaining_seconds(end, 0.1))
            )[0]:
                continue
            raw = os.read(sys.stdin.fileno(), MAX_LINE)
            if not raw:
                raise ValueError("protocol EOF without finish")
            total += len(raw)
            if total > MAX_BYTES:
                raise ValueError("protocol byte budget")
            buffer.extend(raw)
            if len(buffer) > MAX_LINE:
                raise ValueError("protocol line budget")
            if b"\n" not in buffer:
                continue
            line, _, rest = buffer.partition(b"\n")
            if rest:
                raise ValueError("one command at a time")
            buffer.clear()
            command = json.loads(line.decode("utf-8"))
            if (
                not isinstance(command, dict)
                or type(command.get("seq")) is not int
                or command["seq"] != sequence + 1
            ):
                raise ValueError("protocol sequence")
            sequence += 1
            operation_seconds = {"health": 1, "ranking": 35, "begin": 35}.get(
                command.get("op")
            )
            if operation_seconds is not None:
                command_deadline = min(
                    command_deadline, time.monotonic() + operation_seconds
                )
            with absolute_watchdog(command_deadline):
                result = client.handle(command)
            if result["outcome"] == "finished":
                emit("finished", pending=0, idle=0)
                return
            emit(
                "reply",
                result=result,
                pending=len(client.pending),
                idle=len(client.idle),
            )
        raise ValueError("command budget")
    except (Exception, KeyboardInterrupt, SystemExit) as error:  # noqa: BLE001 - fixed protocol failure closes all sockets and exits
        failed_deadline = min(command_deadline, client.end())
        client.close_all()  # Reporting must never retain a socket or renew its deadline.
        try:
            emitter.emit(
                "failed",
                sequence,
                deadline=failed_deadline,
                exception_type=type(error).__name__,
            )
        except (ValueError, OSError):
            pass  # No further output after an output-budget/write failure.
        raise SystemExit(1) from None
    finally:
        client.close_all()


if __name__ == "__main__":
    main()
