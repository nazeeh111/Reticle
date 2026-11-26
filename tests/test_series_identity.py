import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import tifffile

from reticle.batch import compare_batch, recheck_report
from reticle.cli import main


class SeriesIdentityTests(unittest.TestCase):
    def test_names_and_legacy_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, exported = root / "source.ome.tif", root / "export.ome.tif"
            for path in (source, exported):
                with tifffile.TiffWriter(path, ome=True) as tif:
                    for name in ("first <slide>", 'second & "slide"'):
                        tif.write(np.zeros((8, 8), dtype="uint16"), metadata={
                            "axes": "YX", "Name": name, "PhysicalSizeX": .25, "PhysicalSizeY": .25,
                        })
            report = compare_batch([{"source": source, "export": exported, "source_series": 1, "export_series": 0}])
            pair = report["pairs"][0]
            self.assertEqual(pair["source_series_name"], 'second & "slide"')
            self.assertEqual(pair["export_series_name"], "first <slide>")
            self.assertEqual(pair["comparison"]["axes"][0]["source"]["unit"], "µm")
            recheck_report(report)
            altered = copy.deepcopy(report)
            del altered["pairs"][0]["source_series_name"]
            with self.assertRaises(ValueError):
                recheck_report(altered)
            legacy = copy.deepcopy(report)
            legacy["receipt_policy"] = "reticle-metadata-1"
            del legacy["pairs"][0]["source_series_name"]
            del legacy["pairs"][0]["export_series_name"]
            recheck_report(legacy)
            legacy["pairs"][0]["receipt"]["source"]["sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                recheck_report(legacy)
            html = io.StringIO()
            with contextlib.redirect_stdout(html):
                self.assertEqual(main([str(source), str(exported), "--source-series", "1", "--export-series", "0", "--format", "html"]), 0)
            self.assertIn("second &amp; &quot;slide&quot;", html.getvalue())
            self.assertIn("first &lt;slide&gt;", html.getvalue())
            self.assertNotIn("first <slide>", html.getvalue())
            self.assertIn('role="region"', html.getvalue())
            self.assertIn("confirm specimen identity separately", html.getvalue())
            self.assertIn("overflow-wrap:anywhere", html.getvalue())
            text = io.StringIO()
            with contextlib.redirect_stdout(text):
                self.assertEqual(main([str(source), str(exported), "--source-series", "1", "--export-series", "0"]), 0)
            self.assertIn("may be sensitive", text.getvalue())
            self.assertIn("confirm specimen identity separately", text.getvalue())
            plain = root / "plain.tif"
            tifffile.imwrite(plain, np.zeros((8, 8), dtype="uint16"))
            p = compare_batch([{"source": plain, "export": plain}])["pairs"][0]
            self.assertEqual(p["source_series_name"], "TIFF pages")
            self.assertEqual(p["export_series_name"], "TIFF pages")
