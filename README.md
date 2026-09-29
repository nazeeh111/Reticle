# Reticle

Compare physical calibration metadata before and after a microscopy TIFF export.

A file can retain every pixel while losing its Z spacing or changing its recorded pixel size. Reticle distinguishes missing, changed and equivalent calibration, including equivalent values written in different units. It reads images locally and produces text, JSON or a self-contained HTML report.

## Run

Python 3.12 or later:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install .
python examples/make_fixtures.py
reticle examples/source.ome.tif examples/changed.ome.tif
reticle examples/source.ome.tif examples/unit-equivalent.ome.tif --format html --output comparison.html
```

The synthetic fixture generator writes only to `examples/`. The changed export has identical pixels and doubles the recorded Z spacing from 1.5 to 3 µm. The equivalent export records X spacing as 250 nm instead of 0.25 µm. Open the HTML report in a browser; it contains no image pixels, scripts or remote assets.

Exit codes: `0` means required calibration values agree and the supported plane mapping was checked; `1` means a calibration or dimension difference, or missing required calibration; `2` means a file, mapping or input could not be checked. Agreement does not prove instrument accuracy or pixel equality.

## Select the image series

A multi-series file requires an explicit zero-based index. Reticle does not pair images by similar names or assume that matching OME IDs prove their identity.

```sh
reticle source.ome.tif exported.ome.tif --source-series 1 --export-series 0
```

For batch work, provide explicit pairs in a JSON manifest. Paths are relative to the manifest:

```json
[
  {"source": "raw/sample-a.ome.tif", "export": "export/sample-a.ome.tif"},
  {"source": "raw/series.ome.tif", "export": "export/series.ome.tif", "source_series": 1, "export_series": 0}
]
```

```sh
reticle --manifest pairs.json --format json --output calibration.json
```

Reports never overwrite existing files or input paths. A failed pair is included in the report and does not suppress results from other pairs.
Each pair has a verdict: verified agreement, differences found, or agreement cannot be established. The report keeps manifest-relative paths so equally named files remain distinguishable.

## What is checked

- Spatial calibration values, normalized to micrometres with their original value, unit and metadata source retained.
- Recorded X/Y/Z/C/T dimensions where available.
- Supported single-file scalar OME-TIFF plane mappings, so metadata is not silently attached to the wrong image series.
- A supported OME scalar numeric pixel type matching each mapped TIFF plane's declared type.
- Ordinary scalar TIFF X/Y resolution declarations. These are labeled as TIFF resolution rather than independently measured microscope calibration.

Missing calibration is never assumed to be 1 µm/pixel. Z spacing is optional when both selected images are known to have one Z plane and neither declares Z calibration. Unsupported layouts and metadata are reported as unverified, not quietly accepted.

Reticle is a metadata comparison, not a pixel comparison, image registration tool, calibration procedure, or full OME schema validator. It does not establish acquisition quality, instrument accuracy or scientific validity. See [design and scope](docs/design.md).

## Development

```sh
python -m unittest discover -s tests -v
```

Synthetic fixtures test metadata changes independently of pixel content. No private microscopy data is included.
For a release check, build a wheel with `python -m pip wheel --no-deps --wheel-dir dist .`, install it in a fresh virtual environment, and run its `reticle` command from outside this checkout with `PYTHONPATH` unset. Run `python scripts/verify_workflow.py` against the generated examples and check both batch reports and output-file refusal. Local check results and remaining limits belong in the release evidence; a local pass does not stand in for a live CI run.

## Related tools

[Fiji](https://imagej.net/software/fiji/) and [Bio-Formats](https://www.openmicroscopy.org/bio-formats/) provide image inspection and conversion. Reticle complements them with an explicit source/export comparison. The TIFF reader is [tifffile](https://github.com/cgohlke/tifffile), and XML is parsed with [defusedxml](https://github.com/tiran/defusedxml). Their licenses remain applicable to those dependencies. Original Reticle code is MIT licensed.
