import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import tifffile

from reticle.cli import main


class ProgressTests(unittest.TestCase):
    def test_progress_is_stderr_only_and_keeps_mixed_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, spacing in (("source", 1.5), ("changed", 3.0)):
                tifffile.imwrite(
                    root / f"{name}.ome.tif", np.zeros((3, 4, 5), dtype="uint16"), ome=True,
                    metadata={"axes": "ZYX", "PhysicalSizeX": .25, "PhysicalSizeY": .25,
                              "PhysicalSizeZ": spacing},
                )
            pairs = [{"source": "source.ome.tif", "export": "source.ome.tif"},
                     {"source": "source.ome.tif", "export": "changed.ome.tif"},
                     {"source": "source.ome.tif", "export": "missing.tif"}]
            manifest = root / "pairs.json"
            manifest.write_text(json.dumps(pairs))
            plain, observed, stderr = io.StringIO(), io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(plain):
                self.assertEqual(main(["--manifest", str(manifest), "--format", "json"]), 2)
            with contextlib.redirect_stdout(observed), contextlib.redirect_stderr(stderr):
                self.assertEqual(main(["--manifest", str(manifest), "--format", "json", "--progress"]), 2)
            self.assertEqual(json.loads(plain.getvalue()), json.loads(observed.getvalue()))
            self.assertEqual(stderr.getvalue().splitlines(), [
                "reticle: pair 1/3: inspecting", "reticle: pair 1/3: agreement",
                "reticle: pair 2/3: inspecting", "reticle: pair 2/3: differences",
                "reticle: pair 3/3: inspecting", "reticle: pair 3/3: unverified",
            ])
            self.assertNotIn(str(root), stderr.getvalue())
            output = root / "existing.json"
            output.write_text("untouched")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(main(["--manifest", str(manifest), "--output", str(output), "--progress"]), 2)
            self.assertNotIn("inspecting", stderr.getvalue())
            self.assertEqual(output.read_text(), "untouched")
