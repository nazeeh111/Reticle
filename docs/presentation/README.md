# The same array can describe a different distance

Actual current-main `7b2ef38b7506aabc01745b3eae68ff035960c1de`, Reticle `0.1.1.dev0`. This new run uses only the repository's generated synthetic TIFFs. It is not microscopy acquisition, instrument calibration or a new accuracy study.

The unchanged fixture generator independently decodes all four files and confirms the same `3 × 8 × 12` uint16 array: 288 samples. **Reticle itself does not decode or compare pixels.** It inspects the declared TIFF/OME metadata and supported plane mapping from exact captured input bytes.

## Inspect the actual outputs

- [Mixed three-pair HTML report](comparison.html), [JSON receipt](comparison.json), [pair manifest](pairs.json).
- Individual receipts: [changed Z](changed.json), [equivalent X units](unit-equivalent.json), [ordinary TIFF](plain.json).
- [Executed journey and controls](journey.json), [fixture observations](inputs/observations.json), [original generator](inputs/make_fixtures.py).
- [Wide SVG](spacing.svg), [phone SVG](spacing-mobile.svg), [figure source](figure.py), [figure manifest](figure-manifest.json).

GitHub shows HTML source; download the worked ZIP linked in the root README, extract, and open `comparison.html` locally. No JavaScript, remote asset or image pixels are embedded in the native report. It is a saved evidence view, not a browser upload or analysis application.

| Comparison | X/Y | Z and mapping | Exit |
| --- | --- | --- | --- |
| Source → changed OME | Same | 1.5 → 3 µm; supported mapping checked | 1 |
| Source → unit-equivalent OME | 0.25 µm = 250 nm | Same; supported mapping checked | 0 |
| Source → ordinary TIFF | Resolution declarations match | Z lost; mapping unverified | 2 |

The batch exits 2 and retains all three results. A single unverified pair does not erase the changed and agreeing pairs. Only metadata agreement within relative tolerance 1e-9 is tested; this does not establish instrument accuracy, specimen meaning or pixel equality. The old 0.1.0 report/capture remain separate and unchanged in `docs/`.

## Read the figure

Each of the 288 source sample values is displayed once in each comparison panel. The grayscale mapping is common and linear: `round(value × 255 / 287)`, native 12×8 cells, no interpolation. Grayscale is an orientation preview of these synthetic fixtures, not a specimen contrast adjustment. The two TIFFs have identical sample arrays by the independent fixture check.

Rulers use the same linear 0–6 µm scale. Relative plane centers are `index × recorded Z spacing`: source 0/1.5/3 and changed export 0/3/6 µm. **Zero is chosen for illustration**; the files do not establish an absolute Z origin or acquisition position. Thumbnail height does not depict slice thickness. There is no perspective, volume or physical-accuracy claim. Exact metadata, units, and verdicts remain in the JSON and native report.

## Reopen and recompute

After extracting the complete worked archive:

```sh
python3 -I -B reopen.py
```

The standard-library route checks every manifest byte, recorded classifications and receipt hashes. It is a read-only recorded-evidence check, not a new TIFF parse or origin authentication. Original JSON receipts contain the producer's synthetic absolute paths; `reticle --recheck` deliberately uses those original paths and is not a portable path-remapping command.

To inspect the extracted TIFFs again, first install the pinned current-source Reticle and its declared dependencies, then run:

```sh
python3 -I -B reopen.py --native
```

This route creates a fresh comparison using paths inside the extraction, requires the same input SHA-256/byte lengths and complete metadata findings, writes a new receipt only in temporary storage, and rechecks that new receipt. It does not rewrite or pretend to recheck the original absolute paths. The native source/dependencies are external to this bundle. The fresh mixed receipt matches with aggregate exit 2, preserving the ordinary TIFF’s unverified outcome. Only recheck trusted reports because their paths select files to read.

## Refusals and source ownership

Actual installed CLI checks retained here cover existing-output refusal, output-equals-input refusal, missing input, a typed receipt change from integer 0 to float 0.0, and post-receipt byte mutation. Appending bytes left metadata findings unchanged but made the original receipt refuse with exit 2; restoring the exact original bytes made its exit-1 changed-Z receipt match again. Fixture regeneration also refused to overwrite existing outputs.

Reticle snapshots and hashes each full admitted input before metadata inspection. The receipt binds the inspected bytes, not an atomic external acquisition generation. Physical uncertainty, calibration truth and changes after a successful recheck are outside the claim. See the root README and retained design document for limits.

Current main's native report remains unchanged. Its comparison table can be panned on narrow screens, but the pending engineering branch owns explicit keyboard regions, responsive axis findings and HTML receipt disclosure. That branch was not merged here, and this presentation does not claim those controls have shipped. Machine JSON and the local recorded-evidence reader remain available.

All inputs are synthetic, source MIT license and third-party attribution remain retained. No private captures, external scans or cloud service were used.
