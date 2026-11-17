"""A failed report must not occupy its final name or prevent a valid retry."""
import contextlib
import io
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import tifffile

from reticle.cli import load_manifest, main


class ReportIOTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ('source.ome.tif', 'export.ome.tif'):
            tifffile.imwrite(
                self.root / name, np.arange(64, dtype='uint16').reshape(8, 8), ome=True,
                metadata={'axes': 'YX', 'PhysicalSizeX': .25, 'PhysicalSizeY': .25},
            )
        self.manifest = self.root / 'pairs.json'
        self.manifest.write_text(json.dumps([{'source': 'source.ome.tif', 'export': 'export.ome.tif'}]))
        self.target = self.root / 'report.json'
        self.args = ['--manifest', str(self.manifest), '--format', 'json', '--output', str(self.target)]

    def test_real_partial_write_leaves_no_final_and_same_target_retry_succeeds(self):
        def limited():
            signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
            resource.setrlimit(resource.RLIMIT_FSIZE, (128, 128))

        result = subprocess.run(
            [sys.executable, '-m', 'reticle', *self.args], preexec_fn=limited,
            capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.root.glob('.reticle-*.tmp')), [])
        self.assertEqual(main(self.args), 0)
        self.assertEqual(main(['--recheck', str(self.target)]), 0)

    def test_manifest_uses_regular_file_admission_and_enforces_actual_byte_limit(self):
        fifo = self.root / 'manifest.fifo'
        os.mkfifo(fifo)
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'reticle', '--manifest', str(fifo)],
                capture_output=True, timeout=2,
            )
        except subprocess.TimeoutExpired:
            self.fail('Batch manifest admission blocked on a FIFO')
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'regular file', result.stderr)
        with patch('reticle.cli.open_regular', return_value=io.BytesIO(b' ' * (1024 * 1024 + 1))):
            with self.assertRaisesRegex(ValueError, 'Manifest exceeds'):
                load_manifest(self.manifest)

    def test_flush_failure_preserves_absence_and_retry(self):
        with patch.object(os, 'fsync', side_effect=OSError('synthetic sync failure')):
            self.assertEqual(main(self.args), 2)
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.root.glob('.reticle-*.tmp')), [])
        self.assertEqual(main(self.args), 0)

    def test_cleanup_warning_keeps_complete_report_and_foreign_stage_is_not_removed(self):
        warning = io.StringIO()
        with patch('reticle.cli.Path.unlink', side_effect=OSError('synthetic cleanup failure')):
            with contextlib.redirect_stderr(warning):
                self.assertEqual(main(self.args), 0)
        self.assertIn('Report saved at', warning.getvalue())
        self.assertIn('staging cleanup failed', warning.getvalue())
        self.assertEqual(main(['--recheck', str(self.target)]), 0)
        other = self.root / 'other.json'
        stage = self.root / '.reticle-foreign.tmp'
        stage.write_bytes(b'foreign')
        with patch('reticle.cli.uuid4', return_value=SimpleNamespace(hex='foreign')):
            self.assertEqual(main([*self.args[:-1], str(other)]), 2)
        self.assertEqual(stage.read_bytes(), b'foreign')
        self.assertFalse(other.exists())

    def test_long_valid_report_name_remains_supported(self):
        target = self.root / ('x' * 240 + '.json')
        self.assertEqual(main([*self.args[:-1], str(target)]), 0)
        self.assertEqual(main(['--recheck', str(target)]), 0)


if __name__ == '__main__':
    unittest.main()
