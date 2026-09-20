"""
Sensor bridge runtime supervisor and NDJSON protocol parser.
Communicates with OpenRGBTempSync.SensorBridge child process over stdout/stderr.
"""

import collections
import dataclasses
import json
import logging
import math
import os
import subprocess
import threading
import time
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger("SensorRuntime")

MAX_LINE_LENGTH_BYTES = 65536  # 64 KiB


@dataclasses.dataclass
class SensorReading:
    cpu_temp: Optional[float]
    gpu_temp: Optional[float]
    cpu_source: str
    gpu_source: str
    timestamp_utc: str
    warnings: List[str]


class SensorStatus:
    STARTING = "STARTING"
    OK = "OK"
    STALE = "STALE"
    FATAL = "FATAL"
    OFFLINE = "OFFLINE"


class SensorRecordParser:
    """Validates and parses NDJSON lines conforming to schema 1."""

    def __init__(self):
        self._hello_received = False
        self._hello_data: Optional[Dict[str, Any]] = None
        self._last_seq = 0
        self._latest_reading: Optional[SensorReading] = None
        self.last_sample_monotonic = 0.0
        self._fatal_error: Optional[Dict[str, Any]] = None

    def reset(self):
        """Reset parser and sample sequence state for child process restart."""
        self._hello_received = False
        self._hello_data = None
        self._last_seq = 0
        self._latest_reading = None
        self.last_sample_monotonic = 0.0
        self._fatal_error = None

    def is_hello_received(self) -> bool:
        return self._hello_received

    def get_latest_reading(self) -> Optional[SensorReading]:
        return self._latest_reading

    def get_fatal_error(self) -> Optional[Dict[str, Any]]:
        return self._fatal_error

    def is_stale(self, max_age_seconds: float = 10.0) -> bool:
        if self.last_sample_monotonic == 0.0:
            return True
        return (time.monotonic() - self.last_sample_monotonic) > max_age_seconds

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse and validate one line of NDJSON stdout."""
        if not line:
            return None

        # Check line length constraint
        if len(line.encode("utf-8")) > MAX_LINE_LENGTH_BYTES:
            logger.warning("Rejected sensor line exceeding maximum 64 KiB limit")
            return None

        try:
            record = json.loads(line)
        except Exception:
            return None

        if not isinstance(record, dict):
            return None

        # Schema version gate
        if record.get("schema") != 1:
            logger.warning(f"Unsupported sensor record schema version: {record.get('schema')}")
            return None

        rec_type = record.get("type")

        if rec_type == "hello":
            self._hello_received = True
            self._hello_data = record
            return record

        if rec_type == "fatal":
            self._fatal_error = record
            return record

        if rec_type == "sample":
            seq = record.get("seq")
            if not isinstance(seq, int) or seq <= self._last_seq:
                logger.debug(f"Rejected non-monotonic sample seq {seq} (last {self._last_seq})")
                return None

            self._last_seq = seq
            self.last_sample_monotonic = time.monotonic()

            def _parse_temp(val: Any) -> Optional[float]:
                if val is None or isinstance(val, bool):
                    return None
                try:
                    num = float(val)
                    if math.isfinite(num):
                        return num
                except (ValueError, TypeError):
                    pass
                return None

            cpu_c = _parse_temp(record.get("cpu_c"))
            gpu_c = _parse_temp(record.get("gpu_c"))

            cpu_source = str(record.get("cpu_source", "Unknown"))
            gpu_source = str(record.get("gpu_source", "Unknown"))
            timestamp = str(record.get("timestamp_utc", ""))

            warnings: List[str] = []
            raw_warnings = record.get("warnings")
            if isinstance(raw_warnings, list):
                for w in raw_warnings:
                    if isinstance(w, str):
                        w_clean = w.strip()
                        if w_clean and len(w_clean) <= 1024:
                            warnings.append(w_clean)
                    elif isinstance(w, (int, float)) and not isinstance(w, bool):
                        warnings.append(str(w))

            self._latest_reading = SensorReading(
                cpu_temp=cpu_c,
                gpu_temp=gpu_c,
                cpu_source=cpu_source,
                gpu_source=gpu_source,
                timestamp_utc=timestamp,
                warnings=warnings
            )
            return record

        return None


class SensorSupervisor:
    """Supervises the sensor bridge process, restarts on crash, and buffers diagnostics."""

    def __init__(
        self,
        bridge_path: Optional[str] = None,
        interval_ms: int = 1000,
        job_object: Optional[Any] = None
    ):
        self.bridge_path = bridge_path
        self.interval_ms = interval_ms
        self.job_object = job_object
        self.parser = SensorRecordParser()
        self.status = SensorStatus.OFFLINE

        self._process: Optional[subprocess.Popen] = None
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._stderr_buffer: Deque[str] = collections.deque(maxlen=100)
        self._restart_history: List[float] = []
        self._last_start_attempt = 0.0
        self._restart_cooldown_seconds = 1.0

    def get_status(self) -> str:
        if self._process is None or self._process.poll() is not None:
            return SensorStatus.OFFLINE
        if self.parser.get_fatal_error() is not None:
            return SensorStatus.FATAL
        if not self.parser.is_hello_received():
            return SensorStatus.STARTING
        if self.parser.is_stale(max_age_seconds=10.0):
            return SensorStatus.STALE
        return SensorStatus.OK

    def get_latest_reading(self) -> Optional[SensorReading]:
        return self.parser.get_latest_reading()

    def get_recent_stderr(self) -> List[str]:
        return list(self._stderr_buffer)

    def start(self):
        if self._process is not None and self._process.poll() is None:
            return

        if not self.bridge_path or not os.path.exists(self.bridge_path):
            logger.info(f"Sensor bridge executable not present at {self.bridge_path}. Offline mode active.")
            self.status = SensorStatus.OFFLINE
            return

        # Check restart budget (max 3 restarts within 60s)
        now = time.monotonic()
        self._restart_history = [t for t in self._restart_history if now - t < 60.0]
        if len(self._restart_history) >= 3:
            logger.error("Sensor bridge exceeded restart limit (3 in 60s). Marking FATAL.")
            self.status = SensorStatus.FATAL
            return

        # Reset parser sequence and sample state for each new child process
        self.parser.reset()
        self._restart_history.append(now)
        self._last_start_attempt = now
        self._stop_event.clear()
        self.status = SensorStatus.STARTING

        args = [self.bridge_path, "--interval", str(self.interval_ms)]

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
                creationflags=creationflags
            )
            if self.job_object and self._process:
                try:
                    if hasattr(self._process, "_handle"):
                        self.job_object.assign_process(self._process._handle)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Failed to launch sensor bridge: {e}")
            self.status = SensorStatus.FATAL
            return

        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def maybe_restart(self) -> bool:
        """Restart an exited, fatal, or stale helper once the cooldown permits."""
        status = self.get_status()
        if status not in (SensorStatus.OFFLINE, SensorStatus.STALE, SensorStatus.FATAL):
            return False

        now = time.monotonic()
        if now - self._last_start_attempt < self._restart_cooldown_seconds:
            return False

        # Tear down a stale/fatal live process before starting a fresh parser session.
        if self._process is not None:
            self.stop()
        self.start()
        return self.get_status() == SensorStatus.STARTING

    def _read_stdout(self):
        proc = self._process
        if not proc or not proc.stdout:
            return

        for line in iter(proc.stdout.readline, ""):
            if self._stop_event.is_set():
                break
            stripped = line.strip()
            if stripped:
                self.parser.parse_line(stripped)

    def _read_stderr(self):
        proc = self._process
        if not proc or not proc.stderr:
            return

        for line in iter(proc.stderr.readline, ""):
            if self._stop_event.is_set():
                break
            stripped = line.strip()
            if stripped:
                self._stderr_buffer.append(stripped)
                logger.debug(f"[SensorBridge stderr] {stripped}")

    def stop(self):
        self._stop_event.set()
        proc = self._process
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._process = None
        self.parser.reset()
        self.status = SensorStatus.OFFLINE
