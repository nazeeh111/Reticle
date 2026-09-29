"""Behavioral checks using small TIFFs with independently specified metadata."""

import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import tifffile

from reticle.cli import exit_status
from reticle.core import compare_series, inspect_file

NAMESPACE = "http://www.openmicroscopy.org/Schemas/OME/2016-06"


def ome_xml(images):
    return f'<OME xmlns="{NAMESPACE}">' + "".join(images) + "</OME>"


def image_xml(
    index=0,
    *,
    shape=(4, 3, 2, 1, 1),
    calibration="",
    mapping="<TiffData/>",
    order="XYZCT",
    pixel_type="uint16",
):
    x, y, z, c, t = shape
    return (
        f'<Image ID="Image:{index}" Name="Series {index}"><Pixels ID="Pixels:{index}" '
        f'DimensionOrder="{order}" Type="{pixel_type}" SizeX="{x}" SizeY="{y}" '
        f'SizeZ="{z}" SizeC="{c}" SizeT="{t}" {calibration}>'
        f"{mapping}</Pixels></Image>"
    )


def write_ome(path, xml, count=2, y=3, x=4):
    pixels = np.arange(count * y * x, dtype=np.uint16).reshape(count, y, x)
    # tifffile's generic ImageDescription writer is ASCII; XML character references
    # still exercise the Unicode OME unit after parsing.
    tifffile.imwrite(
        path,
        pixels,
        metadata=None,
        photometric="minisblack",
        description=xml.replace("µ", "&#181;"),
    )


def axes_by_name(result):
    return {axis["axis"]: axis for axis in result["axes"]}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_ome_unit_equivalence_and_changed_y(self):
        base = 'PhysicalSizeX="0.25" PhysicalSizeXUnit="µm" PhysicalSizeY="0.25" PhysicalSizeYUnit="µm" PhysicalSizeZ="1.5" PhysicalSizeZUnit="µm"'
        equivalent = 'PhysicalSizeX="250" PhysicalSizeXUnit="nm" PhysicalSizeY="0.00025" PhysicalSizeYUnit="mm" PhysicalSizeZ="1.5" PhysicalSizeZUnit="µm"'
        changed = 'PhysicalSizeX="0.25" PhysicalSizeXUnit="µm" PhysicalSizeY="0.5" PhysicalSizeYUnit="µm" PhysicalSizeZ="1.5" PhysicalSizeZUnit="µm"'
        for name, calibration in [("base", base), ("equivalent", equivalent), ("changed", changed)]:
            write_ome(self.root / f"{name}.ome.tif", ome_xml([image_xml(calibration=calibration)]))
        source = inspect_file(self.root / "base.ome.tif")["series"][0]
        same = compare_series(source, inspect_file(self.root / "equivalent.ome.tif")["series"][0])
        difference = compare_series(
            source, inspect_file(self.root / "changed.ome.tif")["series"][0]
        )
        self.assertTrue(same["verified"])
        self.assertEqual([axis["status"] for axis in same["axes"]], ["same", "same", "same"])
        self.assertEqual(axes_by_name(same)["X"]["export"]["micrometres"], "0.250")
        self.assertEqual(axes_by_name(same)["Y"]["export"]["micrometres"], "0.25000")
        self.assertEqual(axes_by_name(difference)["Y"]["status"], "changed")
        self.assertEqual(axes_by_name(difference)["X"]["status"], "same")

    def test_ome_pixel_type_mismatch_blocks_verified_agreement(self):
        path = self.root / "wrong-type.ome.tif"
        xml = ome_xml(
            [
                image_xml(
                    shape=(4, 3, 1, 1, 1),
                    calibration='PhysicalSizeX="1" PhysicalSizeY="1"',
                    pixel_type="uint16",
                )
            ]
        )
        tifffile.imwrite(
            path,
            np.zeros((3, 4), dtype=np.uint8),
            metadata=None,
            photometric="minisblack",
            description=xml,
        )
        with mock.patch.object(
            tifffile.TiffPage, "asarray", side_effect=AssertionError("decoded pixels")
        ):
            series = inspect_file(path)["series"][0]
        self.assertFalse(series["verified_mapping"])
        self.assertIn("pixel_type_mismatch", [issue["code"] for issue in series["issues"]])
        comparison = compare_series(series, series)
        self.assertFalse(comparison["verified"])
        self.assertEqual(
            exit_status({"pairs": [{"comparison": comparison, "issues": series["issues"]}]}), 2
        )

    def test_ordinary_tiff_resolution_and_lost_z(self):
        source_cal = 'PhysicalSizeX="0.25" PhysicalSizeY="0.25" PhysicalSizeZ="1.5"'
        write_ome(self.root / "source.ome.tif", ome_xml([image_xml(calibration=source_cal)]))
        plain = self.root / "plain.tif"
        tifffile.imwrite(
            plain,
            np.zeros((2, 3, 4), dtype=np.uint16),
            metadata=None,
            photometric="minisblack",
            resolution=(40000, 40000),
            resolutionunit="CENTIMETER",
        )
        original = inspect_file(self.root / "source.ome.tif")["series"][0]
        exported = inspect_file(plain)["series"][0]
        result = compare_series(original, exported)
        self.assertEqual(exported["calibration"]["X"]["micrometres"], "0.25")
        self.assertEqual(exported["calibration"]["Y"]["micrometres"], "0.25")
        self.assertIsNone(exported["calibration"]["Z"])
        self.assertEqual(axes_by_name(result)["Z"]["status"], "lost")
        self.assertFalse(result["verified"])
        self.assertIn("unlabeled_pages", [issue["code"] for issue in exported["issues"]])

    def test_default_unit_partial_calibration_and_unknown_unit(self):
        xml = ome_xml(
            [
                image_xml(
                    calibration='PhysicalSizeX="0.4" PhysicalSizeZ="2" PhysicalSizeZUnit="furlong"'
                )
            ]
        )
        write_ome(self.root / "partial.ome.tif", xml)
        series = inspect_file(self.root / "partial.ome.tif")["series"][0]
        self.assertEqual(series["calibration"]["X"]["unit"], "µm")
        self.assertEqual(series["calibration"]["X"]["micrometres"], "0.4")
        self.assertIsNone(series["calibration"]["Y"])
        self.assertIsNone(series["calibration"]["Z"])
        self.assertFalse(series["verified_mapping"])
        self.assertIn("unsupported_unit", [issue["code"] for issue in series["issues"]])
        known = dict(series)
        known["calibration"] = dict(
            series["calibration"],
            Z={"value": "2", "unit": "µm", "micrometres": "2", "source": "OME PhysicalSize"},
        )
        known["issues"] = []
        self.assertEqual(axes_by_name(compare_series(known, series))["Z"]["status"], "unknown")

    def test_malformed_numeric_and_malicious_xml_are_rejected(self):
        for name, xml in [
            ("nonfinite", ome_xml([image_xml(calibration='PhysicalSizeX="NaN"')])),
            ("zero", ome_xml([image_xml(calibration='PhysicalSizeX="0"')])),
            (
                "huge",
                ome_xml([image_xml(calibration='PhysicalSizeX="1e999999" PhysicalSizeXUnit="m"')]),
            ),
            (
                "tiny",
                ome_xml(
                    [image_xml(calibration='PhysicalSizeX="1e-9999999" PhysicalSizeXUnit="m"')]
                ),
            ),
            (
                "entity",
                '<!DOCTYPE OME [<!ENTITY x "boom">]><OME xmlns="' + NAMESPACE + '">&x;</OME>',
            ),
        ]:
            with self.subTest(name=name):
                path = self.root / f"{name}.ome.tif"
                write_ome(path, xml)
                with self.assertRaises(ValueError):
                    inspect_file(path)

    def test_explicit_multiseries_ifds_and_dimension_order(self):
        # The first series is stored in IFDs 2,3 and the second in IFDs 0,1.
        first = image_xml(
            0,
            shape=(4, 3, 2, 1, 1),
            calibration='PhysicalSizeX="1"',
            mapping='<TiffData IFD="2" FirstZ="0" PlaneCount="2"/>',
        )
        second = image_xml(
            1,
            shape=(4, 3, 1, 1, 2),
            calibration='PhysicalSizeX="2"',
            mapping='<TiffData IFD="1" FirstT="1"/><TiffData IFD="0" FirstT="0"/>',
        )
        path = self.root / "multi.ome.tif"
        write_ome(path, ome_xml([first, second]), count=4)
        result = inspect_file(path)
        self.assertEqual(len(result["series"]), 2)
        self.assertEqual([s["index"] for s in result["series"]], [0, 1])
        self.assertEqual([s["name"] for s in result["series"]], ["Series 0", "Series 1"])
        self.assertTrue(all(s["verified_mapping"] for s in result["series"]))
        self.assertEqual(result["series"][1]["shape"]["T"], 2)

    def test_tiffdata_respects_declared_axis_raster_order(self):
        # For XYCTZ, T varies faster than Z. Starting at T1 leaves exactly
        # three coordinates; interpreting Z as faster would run out of bounds.
        mapping = (
            '<TiffData IFD="0" FirstT="0" PlaneCount="1"/>'
            '<TiffData IFD="1" FirstT="1" PlaneCount="3"/>'
        )
        path = self.root / "xyctz.ome.tif"
        write_ome(
            path,
            ome_xml([image_xml(shape=(4, 3, 2, 1, 2), order="XYCTZ", mapping=mapping)]),
            count=4,
        )
        self.assertTrue(inspect_file(path)["series"][0]["verified_mapping"])

    def test_duplicate_missing_and_out_of_bounds_ifds_are_unverified(self):
        mappings = {
            "duplicate": '<TiffData IFD="0" FirstZ="0"/><TiffData IFD="1" FirstZ="0"/>',
            "missing": '<TiffData IFD="0" FirstZ="0"/>',
            "out_of_bounds": '<TiffData IFD="5" FirstZ="0" PlaneCount="2"/>',
        }
        expected = {
            "duplicate": "duplicate_mapping",
            "missing": "missing_mapping",
            "out_of_bounds": "mapping_out_of_bounds",
        }
        for name, mapping in mappings.items():
            with self.subTest(name=name):
                path = self.root / f"{name}.ome.tif"
                write_ome(path, ome_xml([image_xml(mapping=mapping)]))
                series = inspect_file(path)["series"][0]
                self.assertFalse(series["verified_mapping"])
                self.assertIn(expected[name], [i["code"] for i in series["issues"]])

    def test_bare_tiffdata_ignores_trailing_ifds(self):
        path = self.root / "extra.ome.tif"
        write_ome(path, ome_xml([image_xml()]), count=3)
        series = inspect_file(path)["series"][0]
        self.assertTrue(series["verified_mapping"])
        self.assertEqual(series["issues"], [])

    def test_reused_ifd_invalidates_both_images(self):
        first = image_xml(0, shape=(4, 3, 1, 1, 1), mapping='<TiffData IFD="0"/>')
        second = image_xml(1, shape=(4, 3, 1, 1, 1), mapping='<TiffData IFD="0"/>')
        path = self.root / "reused.ome.tif"
        write_ome(path, ome_xml([first, second]), count=2)
        images = inspect_file(path)["series"]
        self.assertFalse(images[0]["verified_mapping"])
        self.assertFalse(images[1]["verified_mapping"])
        self.assertIn("duplicate_mapping", [i["code"] for i in images[0]["issues"]])

    def test_repeated_tiffdata_is_bounded(self):
        path = self.root / "repeated.ome.tif"
        mapping = '<TiffData IFD="0" PlaneCount="100"/>' * 1000
        write_ome(path, ome_xml([image_xml(mapping=mapping)]))
        issues = inspect_file(path)["series"][0]["issues"]
        self.assertLessEqual(len(issues), 3)
        self.assertIn("duplicate_mapping", [issue["code"] for issue in issues])

    def test_rotated_tiff_is_unverified(self):
        path = self.root / "rotated.tif"
        tifffile.imwrite(
            path,
            np.zeros((3, 4), dtype=np.uint16),
            metadata=None,
            photometric="minisblack",
            resolution=(40000, 40000),
            resolutionunit="CENTIMETER",
            extratags=[(274, "H", 1, 6, False)],
        )
        series = inspect_file(path)["series"][0]
        self.assertFalse(series["verified_mapping"])
        self.assertIn("orientation", [i["code"] for i in series["issues"]])

    def test_external_reference_is_not_followed(self):
        mapping = '<TiffData IFD="0" PlaneCount="2"><UUID FileName="missing.ome.tif">urn:uuid:other</UUID></TiffData>'
        path = self.root / "external.ome.tif"
        write_ome(path, ome_xml([image_xml(mapping=mapping)]))
        with mock.patch.object(
            tifffile.TiffPage, "asarray", side_effect=AssertionError("decoded pixels")
        ):
            result = inspect_file(path)
        series = result["series"][0]
        self.assertFalse(series["verified_mapping"])
        self.assertIn("external_reference", [i["code"] for i in series["issues"]])

    def test_single_plane_missing_z_is_not_required(self):
        xml = ome_xml(
            [image_xml(shape=(4, 3, 1, 1, 1), calibration='PhysicalSizeX="1" PhysicalSizeY="1"')]
        )
        path = self.root / "two_d.ome.tif"
        tifffile.imwrite(
            path,
            np.zeros((3, 4), dtype=np.uint16),
            metadata=None,
            photometric="minisblack",
            description=xml,
        )
        series = inspect_file(path)["series"][0]
        result = compare_series(series, series)
        self.assertTrue(result["verified"])
        self.assertEqual(axes_by_name(result)["Z"]["status"], "unknown")
        self.assertFalse(axes_by_name(result)["Z"]["required"])

    def test_single_page_plain_tiff_has_local_one_plane_shape(self):
        path = self.root / "plain2d.tif"
        tifffile.imwrite(
            path,
            np.zeros((3, 4), dtype=np.uint16),
            metadata=None,
            photometric="minisblack",
            resolution=(100, 100),
            resolutionunit="INCH",
        )
        series = inspect_file(path)["series"][0]
        self.assertEqual(series["shape"], {"X": 4, "Y": 3, "Z": 1, "C": 1, "T": 1})
        self.assertTrue(series["verified_mapping"])
        self.assertIn("local_one_plane", [issue["code"] for issue in series["issues"]])
        result = compare_series(series, series)
        self.assertTrue(result["verified"])
        self.assertFalse(axes_by_name(result)["Z"]["required"])

    def test_missing_resolutionunit_uses_tiff_inch_default(self):
        path = self.root / "default_inch.tif"
        tifffile.imwrite(
            path,
            np.zeros((3, 4), dtype=np.uint16),
            metadata=None,
            photometric="minisblack",
            resolution=(100, 100),
            resolutionunit="INCH",
        )
        data = bytearray(path.read_bytes())
        self.assertEqual(data[:2], b"II")
        ifd = struct.unpack_from("<I", data, 4)[0]
        entry_count = struct.unpack_from("<H", data, ifd)[0]
        entries_start = ifd + 2
        entries = [
            bytes(data[entries_start + 12 * i : entries_start + 12 * (i + 1)])
            for i in range(entry_count)
        ]
        kept = [entry for entry in entries if struct.unpack_from("<H", entry)[0] != 296]
        self.assertEqual(len(kept), entry_count - 1)
        old_next = bytes(
            data[entries_start + 12 * entry_count : entries_start + 12 * entry_count + 4]
        )
        struct.pack_into("<H", data, ifd, len(kept))
        data[entries_start : entries_start + 12 * len(kept)] = b"".join(kept)
        data[entries_start + 12 * len(kept) : entries_start + 12 * len(kept) + 4] = old_next
        path.write_bytes(data)
        series = inspect_file(path)["series"][0]
        self.assertEqual(series["calibration"]["X"]["micrometres"], "254")
        self.assertEqual(series["calibration"]["Y"]["unit"], "pixels/inch")
        self.assertIn("default inch", series["calibration"]["Y"]["source"])


if __name__ == "__main__":
    unittest.main()
