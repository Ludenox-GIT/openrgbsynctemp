import unittest
import sys
import os
import time
from unittest.mock import Mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from openrgb_temp_sync.sensor_runtime import (
    SensorRecordParser,
    SensorReading,
    SensorStatus
)

class TestSensorRuntime(unittest.TestCase):
    def setUp(self):
        self.parser = SensorRecordParser()

    def test_parse_hello_record(self):
        line = '{"schema": 1, "type": "hello", "bridge_version": "1.0.0", "library_version": "0.9.6", "pid": 1234, "interval_ms": 1000}'
        rec = self.parser.parse_line(line)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["type"], "hello")
        self.assertEqual(rec["pid"], 1234)
        self.assertTrue(self.parser.is_hello_received())

    def test_parse_sample_record_monotonic(self):
        self.parser.parse_line('{"schema": 1, "type": "hello", "bridge_version": "1.0.0", "library_version": "0.9.6", "pid": 1234, "interval_ms": 1000}')

        sample1 = '{"schema": 1, "type": "sample", "seq": 1, "timestamp_utc": "2026-09-19T10:00:00Z", "cpu_c": 45.5, "gpu_c": 52.0, "cpu_source": "CPU Core", "gpu_source": "GPU Core", "warnings": []}'
        r1 = self.parser.parse_line(sample1)
        self.assertIsNotNone(r1)
        reading = self.parser.get_latest_reading()
        self.assertIsNotNone(reading)
        self.assertEqual(reading.cpu_temp, 45.5)
        self.assertEqual(reading.gpu_temp, 52.0)
        self.assertEqual(reading.cpu_source, "CPU Core")
        self.assertEqual(reading.gpu_source, "GPU Core")

        sample2 = '{"schema": 1, "type": "sample", "seq": 2, "timestamp_utc": "2026-09-19T10:00:01Z", "cpu_c": 46.0, "gpu_c": 53.0, "cpu_source": "CPU Core", "gpu_source": "GPU Core", "warnings": []}'
        r2 = self.parser.parse_line(sample2)
        self.assertIsNotNone(r2)
        self.assertEqual(self.parser.get_latest_reading().cpu_temp, 46.0)

    def test_reject_non_monotonic_sequence(self):
        self.parser.parse_line('{"schema": 1, "type": "hello", "bridge_version": "1.0.0", "library_version": "0.9.6", "pid": 1234, "interval_ms": 1000}')
        self.parser.parse_line('{"schema": 1, "type": "sample", "seq": 5, "timestamp_utc": "2026-09-19T10:00:00Z", "cpu_c": 45.5, "gpu_c": 52.0, "cpu_source": "CPU Core", "gpu_source": "GPU Core", "warnings": []}')
        bad_sample = '{"schema": 1, "type": "sample", "seq": 3, "timestamp_utc": "2026-09-19T10:00:01Z", "cpu_c": 46.0, "gpu_c": 53.0, "cpu_source": "CPU Core", "gpu_source": "GPU Core", "warnings": []}'
        r = self.parser.parse_line(bad_sample)
        self.assertIsNone(r)
        self.assertEqual(self.parser.get_latest_reading().cpu_temp, 45.5)

    def test_parser_reset_on_restart(self):
        # Initial session with samples up to seq 25
        self.parser.parse_line('{"schema": 1, "type": "hello", "bridge_version": "1.0.0", "library_version": "0.9.6", "pid": 1234, "interval_ms": 1000}')
        self.parser.parse_line('{"schema": 1, "type": "sample", "seq": 25, "timestamp_utc": "2026-09-19T10:00:25Z", "cpu_c": 50.0, "gpu_c": 60.0, "cpu_source": "CPU Core", "gpu_source": "GPU Core", "warnings": []}')
        self.assertEqual(self.parser.get_latest_reading().cpu_temp, 50.0)

        # Bridge restarts; parser is reset
        self.parser.reset()
        self.assertFalse(self.parser.is_hello_received())
        self.assertEqual(self.parser._last_seq, 0)

        # New bridge process emits hello and restarts sequence at 1
        self.parser.parse_line('{"schema": 1, "type": "hello", "bridge_version": "1.0.0", "library_version": "0.9.6", "pid": 5678, "interval_ms": 1000}')
        restarted_sample = '{"schema": 1, "type": "sample", "seq": 1, "timestamp_utc": "2026-09-19T10:01:00Z", "cpu_c": 41.0, "gpu_c": 49.0, "cpu_source": "CPU Core", "gpu_source": "GPU Core", "warnings": []}'
        r = self.parser.parse_line(restarted_sample)
        self.assertIsNotNone(r)
        self.assertEqual(self.parser.get_latest_reading().cpu_temp, 41.0)

    def test_reject_non_finite_temperatures(self):
        self.parser.parse_line('{"schema": 1, "type": "hello", "bridge_version": "1.0.0", "library_version": "0.9.6", "pid": 1234, "interval_ms": 1000}')

        # NaN and Infinity string inputs
        sample_nan = '{"schema": 1, "type": "sample", "seq": 1, "timestamp_utc": "2026-09-19T10:00:00Z", "cpu_c": "NaN", "gpu_c": "Infinity", "cpu_source": "CPU Core", "gpu_source": "GPU Core", "warnings": []}'
        r1 = self.parser.parse_line(sample_nan)
        self.assertIsNotNone(r1)
        reading1 = self.parser.get_latest_reading()
        self.assertIsNone(reading1.cpu_temp)
        self.assertIsNone(reading1.gpu_temp)

        # -Infinity input
        sample_neginf = '{"schema": 1, "type": "sample", "seq": 2, "timestamp_utc": "2026-09-19T10:00:01Z", "cpu_c": "-Infinity", "gpu_c": 58.2, "cpu_source": "CPU Core", "gpu_source": "GPU Core", "warnings": []}'
        r2 = self.parser.parse_line(sample_neginf)
        self.assertIsNotNone(r2)
        reading2 = self.parser.get_latest_reading()
        self.assertIsNone(reading2.cpu_temp)
        self.assertEqual(reading2.gpu_temp, 58.2)

    def test_malformed_warnings_safe(self):
        self.parser.parse_line('{"schema": 1, "type": "hello", "bridge_version": "1.0.0", "library_version": "0.9.6", "pid": 1234, "interval_ms": 1000}')

        # String instead of list
        sample_str = '{"schema": 1, "type": "sample", "seq": 1, "timestamp_utc": "2026-09-19T10:00:00Z", "cpu_c": 45.0, "gpu_c": 50.0, "cpu_source": "CPU Core", "gpu_source": "GPU Core", "warnings": "malformed string warning"}'
        r1 = self.parser.parse_line(sample_str)
        self.assertIsNotNone(r1)
        self.assertEqual(self.parser.get_latest_reading().warnings, [])

        # Mixed array with nulls, dicts, numbers, and strings
        sample_mixed = '{"schema": 1, "type": "sample", "seq": 2, "timestamp_utc": "2026-09-19T10:00:01Z", "cpu_c": 45.0, "gpu_c": 50.0, "cpu_source": "CPU Core", "gpu_source": "GPU Core", "warnings": [null, {"bad": 1}, 500, "  Sensor high temp  "]}'
        r2 = self.parser.parse_line(sample_mixed)
        self.assertIsNotNone(r2)
        self.assertEqual(self.parser.get_latest_reading().warnings, ["500", "Sensor high temp"])

    def test_reject_unsupported_schema(self):
        line = '{"schema": 99, "type": "hello"}'
        self.assertIsNone(self.parser.parse_line(line))

    def test_reject_line_length_over_64k(self):
        huge_line = '{"schema": 1, "type": "sample", "pad": "' + ('A' * 70000) + '"}'
        self.assertIsNone(self.parser.parse_line(huge_line))

    def test_parse_fatal_record(self):
        line = '{"schema": 1, "type": "fatal", "code": 30, "message": "No usable CPU or GPU sensor found"}'
        r = self.parser.parse_line(line)
        self.assertIsNotNone(r)
        self.assertEqual(r["code"], 30)
        self.assertIn("No usable", r["message"])

    def test_stale_detection(self):
        self.parser.parse_line('{"schema": 1, "type": "hello", "bridge_version": "1.0.0", "library_version": "0.9.6", "pid": 1234, "interval_ms": 1000}')
        self.parser.parse_line('{"schema": 1, "type": "sample", "seq": 1, "timestamp_utc": "2026-09-19T10:00:00Z", "cpu_c": 45.5, "gpu_c": 52.0, "cpu_source": "CPU Core", "gpu_source": "GPU Core", "warnings": []}')
        self.assertFalse(self.parser.is_stale(max_age_seconds=5.0))
        self.parser.last_sample_monotonic = time.monotonic() - 12.0
        self.assertTrue(self.parser.is_stale(max_age_seconds=10.0))

    def test_supervisor_reports_starting_until_hello(self):
        from openrgb_temp_sync.sensor_runtime import SensorSupervisor

        supervisor = SensorSupervisor(bridge_path=None)

        class LiveProcess:
            def poll(self):
                return None

        supervisor._process = LiveProcess()
        self.assertEqual(supervisor.get_status(), SensorStatus.STARTING)
        supervisor.parser.parse_line('{"schema":1,"type":"hello","bridge_version":"1","library_version":"1","pid":1,"interval_ms":1000}')
        self.assertEqual(supervisor.get_status(), SensorStatus.STALE)

    def test_supervisor_restart_cooldown_prevents_hot_loop(self):
        from openrgb_temp_sync.sensor_runtime import SensorSupervisor

        supervisor = SensorSupervisor(bridge_path=None)
        supervisor._last_start_attempt = time.monotonic()
        supervisor.start = Mock()
        self.assertFalse(supervisor.maybe_restart())
        supervisor.start.assert_not_called()

if __name__ == '__main__':
    unittest.main()
