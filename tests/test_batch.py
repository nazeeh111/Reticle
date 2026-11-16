import hashlib
import contextlib
import io
import copy
import os
import subprocess
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import tifffile
from reticle.batch import compare_batch, recheck_report, inspect_snapshot
from reticle.cli import main


class BatchReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a = self.root / 'a.ome.tif'
        self.b = self.root / 'b.ome.tif'
        data = np.arange(64, dtype='uint16').reshape(8, 8)
        for path in (self.a, self.b):
            tifffile.imwrite(path, data, ome=True, metadata={'axes': 'YX', 'PhysicalSizeX': .25, 'PhysicalSizeY': .25})

    def test_receipt_rechecks_and_rejects_mutation_and_tampering(self):
        report = compare_batch([{'source': self.a, 'export': self.b}])
        recheck_report(report)
        self.assertEqual(report['pairs'][0]['receipt']['source']['sha256'], hashlib.sha256(self.a.read_bytes()).hexdigest())
        saved = json.loads(json.dumps(report))
        saved['pairs'][0]['source_series'] = 1
        with self.assertRaises(ValueError): recheck_report(saved)
        with self.b.open('ab') as f: f.write(b'changed')
        with self.assertRaises(ValueError): recheck_report(report)

    def test_snapshot_identity_bound_to_inspected_bytes(self):
        from reticle import batch
        original = batch.inspect_file
        before = self.a.read_bytes()
        def changed(path):
            self.a.write_bytes(b'not the inspected image')
            return original(path)
        with patch('reticle.batch.inspect_file', side_effect=changed):
            _, identity = inspect_snapshot(self.a)
        self.assertEqual(identity['sha256'], hashlib.sha256(before).hexdigest())
        self.assertNotEqual(identity['sha256'], hashlib.sha256(self.a.read_bytes()).hexdigest())

    def test_limit_and_failed_pair_keep_other_evidence(self):
        with patch('reticle.batch.MAX_INPUT_BYTES', 10):
            report = compare_batch([{'source': self.a, 'export': self.b}])
        self.assertIn('size limit', report['pairs'][0]['error'])
        missing = self.root / 'missing'
        report = compare_batch([{'source': self.a, 'export': self.b}, {'source': missing, 'export': self.b}])
        self.assertIn('receipt', report['pairs'][0])
        self.assertIn('error', report['pairs'][1])
        with self.assertRaises(ValueError): recheck_report(report)

    def test_recheck_preserves_boolean_integer_and_float_types(self):
        report = compare_batch([{'source': self.a, 'export': self.b}])
        altered = copy.deepcopy(report)
        altered['pairs'][0]['comparison']['verified'] = 1
        with self.assertRaises(ValueError): recheck_report(altered)
        altered = copy.deepcopy(report)
        altered['pairs'][0]['receipt']['source']['bytes'] = float(altered['pairs'][0]['receipt']['source']['bytes'])
        with self.assertRaises(ValueError): recheck_report(altered)
        recheck_report(report)

    def test_fifo_image_and_receipt_refuse_without_blocking(self):
        fifo = self.root / 'fifo'
        os.mkfifo(fifo)
        for args in ([str(fifo), str(self.b), '--format', 'json'], ['--recheck', str(fifo)]):
            completed = subprocess.run([sys.executable, '-m', 'reticle', *args], capture_output=True, timeout=2)
            self.assertEqual(completed.returncode, 2)
            self.assertIn(b'regular file', completed.stdout + completed.stderr)
        self.assertEqual(main([str(self.a), str(self.b), '--format', 'json', '--output', str(self.root / 'retry.json')]), 0)

    def test_stream_limit_after_size_preflight(self):
        from reticle import batch
        original = batch.open_regular
        def admitted(path, limit, label):
            return original(path, 10**8, label)
        with patch('reticle.batch.MAX_INPUT_BYTES', 10), patch('reticle.batch.open_regular', side_effect=admitted):
            with self.assertRaisesRegex(ValueError, '1 GiB'):
                inspect_snapshot(self.a)

    def test_saved_report_acknowledges_aggregate_and_recheck_preserves_difference(self):
        data = np.arange(64, dtype='uint16').reshape(8, 8)
        tifffile.imwrite(self.b, data, ome=True, metadata={'axes': 'YX', 'PhysicalSizeX': .5, 'PhysicalSizeY': .25})
        report = self.root / 'different.json'
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(main([str(self.a), str(self.b), '--format', 'json', '--output', str(report)]), 1)
        self.assertIn('aggregate exit 1', stderr.getvalue())
        saved = report.read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(['--recheck', str(report)]), 1)
        self.assertIn('aggregate exit 1', output.getvalue())
        self.assertEqual(report.read_bytes(), saved)

    def test_cli_recheck_exit_and_retry(self):
        report = self.root / 'report.json'
        self.assertEqual(main([str(self.a), str(self.b), '--format', 'json', '--output', str(report)]), 0)
        self.assertEqual(main(['--recheck', str(report)]), 0)
        with self.b.open('ab') as f: f.write(b'changed')
        self.assertEqual(main(['--recheck', str(report)]), 2)
