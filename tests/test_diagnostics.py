"""Diagnostics tests use synthetic status, never a live controller."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'recorder', Path(__file__).resolve().parents[1] /
    'scripts/record-cnc-diagnostics.py')
recorder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorder)


class DiagnosticsTests(unittest.TestCase):
    def test_credentials_and_unrelated_payload_are_excluded(self):
        result = recorder.diagnostic_status({
            'control_token': 'operator-secret', 'image': 'private-image',
            'cnc': {'connected': True, 'state': 'Idle', 'control_token': 'x',
                    'job': {'state': 'failed', 'error': 'ALARM:5',
                            'token': 'nested-secret'},
                    'calibration_profiles': {'token': 'profile-secret'}},
            'camera': {'ok': False, 'error': 'unavailable', 'frame': 'private'},
            'cam_preparing': False})
        encoded = json.dumps(result)
        self.assertNotIn('secret', encoded)
        self.assertNotIn('token', encoded)
        self.assertNotIn('private', encoded)
        self.assertEqual(result['cnc']['job']['error'], 'ALARM:5')
        self.assertEqual(result['cnc']['state'], 'Idle')

    def test_json_log_rotates_and_keeps_timestamped_machine_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = recorder.open_log(Path(directory))
            handler = logger.handlers[-1]
            handler.maxBytes = 200
            try:
                for index in range(10):
                    recorder.emit(logger, 'status', sequence=index, cnc={
                        'state': 'Hold', 'job': {'state': 'paused'}})
                logs = list(Path(directory).glob('cnc-diagnostics.jsonl*'))
                self.assertGreater(len(logs), 1)
                self.assertLessEqual(len(logs), 6)
                record = json.loads((Path(directory) /
                                     'cnc-diagnostics.jsonl').read_text())
                self.assertEqual(record['sequence'], 9)
                self.assertEqual(record['cnc']['job']['state'], 'paused')
                self.assertIn('time', record)
            finally:
                handler.close()
                logger.removeHandler(handler)
