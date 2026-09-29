import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reticle.cli import exit_status, load_manifest, main, select_series
from reticle.report import html_report, text_report


class CliTests(unittest.TestCase):
    def test_multiple_series_requires_selection(self):
        document = {"series": [{"index": 0}, {"index": 1}]}
        with self.assertRaisesRegex(ValueError, "select one explicitly"):
            select_series(document, None, "Source")
        self.assertEqual(select_series(document, 1, "Source"), {"index": 1})
        for index in (-1, 2, True, "0"):
            with self.assertRaises(ValueError):
                select_series(document, index, "Source")

    def test_manifest_paths_are_relative_to_manifest_not_cwd(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "pairs.json"
            path.write_text(
                json.dumps([{"source": "in.tif", "export": "out.tif", "source_series": 1}])
            )
            pair = load_manifest(path)[0]
            self.assertEqual(pair["source"], Path(root) / "in.tif")
            self.assertEqual(pair["export"], Path(root) / "out.tif")
            self.assertEqual(pair["source_series"], 1)

    def test_manifest_reports_distinguish_equal_basenames(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = Path(root) / "pairs.json"
            manifest.write_text(
                json.dumps(
                    [
                        {"source": "raw/a/sample.tif", "export": "export/a/sample.tif"},
                        {"source": "raw/b/sample.tif", "export": "export/b/sample.tif"},
                    ]
                )
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(["--manifest", str(manifest), "--format", "json"])
            self.assertEqual(status, 2)
            pairs = json.loads(output.getvalue())["pairs"]
            self.assertEqual([p["source"] for p in pairs], ["raw/a/sample.tif", "raw/b/sample.tif"])
            self.assertEqual(
                [p["export"] for p in pairs],
                ["export/a/sample.tif", "export/b/sample.tif"],
            )
            self.assertNotIn(root, output.getvalue())

    def test_manifest_rejects_ambiguous_or_malformed_fields(self):
        bad = [
            [],
            {},
            [{"source": "s", "export": "e", "source_series": True}],
            [{"source": "s", "export": "e", "unknown": 1}],
            [{"source": "s"}],
            [{"source": "s", "export": ""}],
            [{"source": "s", "export": "e"}] * 101,
        ]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "pairs.json"
            for data in bad:
                with self.subTest(data=str(data)[:100]):
                    path.write_text(json.dumps(data))
                    with self.assertRaises(ValueError):
                        load_manifest(path)

    def test_existing_output_cannot_overwrite_an_input(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "source.tif"
            source.write_bytes(b"original image bytes")
            with (
                patch("reticle.cli.inspect_file") as inspect,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main([str(source), "export.tif", "--output", str(source)]), 2)
                inspect.assert_not_called()
            self.assertEqual(source.read_bytes(), b"original image bytes")

    def test_missing_input_is_not_created_as_report(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "missing.tif"
            with (
                patch("reticle.cli.inspect_file") as inspect,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main([str(source), "export.tif", "--output", str(source)]), 2)
                inspect.assert_not_called()
            self.assertFalse(source.exists())

    def test_broken_output_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "report"
            target = Path(root) / "missing"
            output.symlink_to(target)
            with (
                patch("reticle.cli.inspect_file") as inspect,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main(["source", "export", "--output", str(output)]), 2)
                inspect.assert_not_called()
            self.assertFalse(target.exists())

    def test_failed_pair_is_reported_and_other_pairs_continue(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = Path(root) / "pairs.json"
            manifest.write_text(
                json.dumps([{"source": "a", "export": "b"}, {"source": "c", "export": "d"}])
            )
            output = io.StringIO()
            with patch("reticle.cli.inspect_file", side_effect=ValueError("not a TIFF")) as inspect:
                with contextlib.redirect_stdout(output):
                    status = main(["--manifest", str(manifest), "--format", "json"])
            self.assertEqual(status, 2)
            self.assertEqual(inspect.call_count, 2)
            report = json.loads(output.getvalue())
            self.assertEqual([p["source"] for p in report["pairs"]], ["a", "c"])
            self.assertEqual([p["error"] for p in report["pairs"]], ["not a TIFF", "not a TIFF"])

    def test_exit_status_differences_incomplete_and_nonrequired_z(self):
        pair = {
            "comparison": {
                "verified": True,
                "shape_changes": [],
                "axes": [{"axis": "Z", "status": "unknown", "required": False}],
            },
            "issues": [],
        }
        report = {"pairs": [pair]}
        self.assertEqual(exit_status(report), 0)
        pair["comparison"]["axes"][0]["required"] = True
        self.assertEqual(exit_status(report), 1)
        pair["comparison"]["verified"] = False
        self.assertEqual(exit_status(report), 2)
        report["pairs"].append({"error": "bad file"})
        self.assertEqual(exit_status(report), 2)

    def test_report_escapes_untrusted_filenames_and_messages(self):
        report = {
            "version": "0.1.0",
            "pairs": [
                {
                    "source": "<script>alert(1)</script>",
                    "export": "e",
                    "error": "<img src=x onerror=alert(1)>",
                }
            ],
        }
        html = html_report(report)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("default-src 'none'", html)

    def test_reports_show_pair_verdict_even_when_axes_are_same(self):
        comparison = {
            "verified": False,
            "shape_changes": [],
            "axes": [
                {"axis": "X", "status": "same", "source": None, "export": None},
            ],
        }
        report = {
            "version": "0.1.0",
            "pairs": [
                {
                    "source": "raw/a.tif",
                    "export": "export/a.tif",
                    "source_series": 0,
                    "export_series": 0,
                    "comparison": comparison,
                    "issues": [],
                }
            ],
        }
        self.assertIn("Cannot establish agreement", html_report(report))
        self.assertIn("Cannot establish agreement", text_report(report))


if __name__ == "__main__":
    unittest.main()
