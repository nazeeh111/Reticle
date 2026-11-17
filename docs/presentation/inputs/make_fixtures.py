import json
from pathlib import Path

import numpy as np
import tifffile
from defusedxml import ElementTree as ET

root = Path(__file__).parent
names = ("source.ome.tif", "plain.tif", "unit-equivalent.ome.tif", "changed.ome.tif")
if any((root / name).exists() for name in (*names, "observations.json")):
    raise SystemExit("Fixture output exists; move prior generated fixtures before regenerating.")
pixels = np.arange(3 * 8 * 12, dtype=np.uint16).reshape(3, 8, 12)
metadata = {
    "axes": "ZYX",
    "PhysicalSizeX": 0.25,
    "PhysicalSizeXUnit": "µm",
    "PhysicalSizeY": 0.25,
    "PhysicalSizeYUnit": "µm",
    "PhysicalSizeZ": 1.5,
    "PhysicalSizeZUnit": "µm",
}
tifffile.imwrite(
    root / "source.ome.tif", pixels, ome=True, photometric="minisblack", metadata=metadata
)
tifffile.imwrite(
    root / "plain.tif",
    pixels,
    photometric="minisblack",
    metadata=None,
    resolution=(40000, 40000),
    resolutionunit="CENTIMETER",
)
tifffile.imwrite(
    root / "unit-equivalent.ome.tif",
    pixels,
    ome=True,
    photometric="minisblack",
    metadata={**metadata, "PhysicalSizeX": 250, "PhysicalSizeXUnit": "nm"},
)
tifffile.imwrite(
    root / "changed.ome.tif",
    pixels,
    ome=True,
    photometric="minisblack",
    metadata={**metadata, "PhysicalSizeZ": 3.0},
)
report = []
for path in (root / name for name in sorted(names)):
    with tifffile.TiffFile(path, _multifile=False) as image:
        description = image.pages[0].description
        scale = {}
        if image.is_ome:
            ome = ET.fromstring(description)
            scale = dict(
                next(ome.iter("{http://www.openmicroscopy.org/Schemas/OME/2016-06}Pixels")).attrib
            )
        row = {
            "file": path.name,
            "ifds": len(image.pages),
            "first_plane_pixels": [image.pages[0].imagewidth, image.pages[0].imagelength],
            "resolution_unit": str(image.pages[0].tags["ResolutionUnit"].value),
            "x_resolution": image.pages[0].tags["XResolution"].value,
            "physical_metadata": {k: v for k, v in scale.items() if k.startswith("Physical")},
            "pixels_equal": bool(np.array_equal(image.asarray(), pixels)),
        }
        report.append(row)
assert all(r["pixels_equal"] for r in report)
assert next(r for r in report if r["file"] == "plain.tif")["physical_metadata"] == {}
(root / "observations.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
