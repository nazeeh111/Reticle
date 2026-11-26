# Synthetic calibration comparison figure

`calibration-strip.svg`, `calibration-strip.png`, `calibration-strip-mobile.svg` and `calibration-strip-mobile.png` present the retained synthetic result in `comparison.json` and synthetic values from `journey.json`. `calibration-strip.py` checks the recorded values and fixture shape, then generates the SVGs; the PNGs are local Chrome renders of those SVGs. The original figure and worked archive remain unchanged.

Each thumbnail is a 12 × 8 synthetic plane from the retained fixture, drawn using a shared linear mapping `round(value × 255 / 287)`, without interpolation. The generator separately checked all 288 source and export samples for equality; Reticle itself does not compare pixels. Zero is chosen for illustration, and thumbnail height does not represent section thickness or an observed specimen. Common relative-Z ruler coordinates are `plane index × declared spacing`, with 1.5 µm and 3 µm recorded in the two files. This figure does not establish acquisition positions or physical calibration.

The source fixture generator and complete report are in the [worked example](README.md); source code is MIT licensed. No private or patient imagery is used. Missing calibration, equivalent units and unverified plane mapping remain in the native [comparison report](comparison.html) and [receipt](comparison.json).
