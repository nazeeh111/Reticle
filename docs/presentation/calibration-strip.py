"""Draw a comparison from the retained synthetic fixture and native JSON receipt."""
from pathlib import Path
import html
import json

HERE = Path(__file__).resolve().parent
receipt = json.loads((HERE / "comparison.json").read_text())
fixture = json.loads((HERE / "journey.json").read_text())
changed, equivalent, ordinary = receipt["pairs"]
axis = {item["axis"]: item for item in changed["comparison"]["axes"]}
assert axis["Z"]["status"] == "changed"
assert [axis["Z"][k]["micrometres"] for k in ("source", "export")] == ["1.5", "3.0"]
assert fixture["shape"] == [3, 8, 12] and fixture["all288SamplesEqualAcross4Fixtures"]
assert equivalent["comparison"]["verified"] and not ordinary["comparison"]["verified"]


def figure(phone):
    width, height = (720, 1050) if phone else (1200, 620)
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc"><title id="title">Synthetic TIFF calibration before and after export</title><desc id="desc">A source and export with the same synthetic samples declare Z spacing of 1.5 and 3 micrometres. Relative plane centers use a chosen zero, not a measured origin. Reticle inspects metadata, not pixel equality or physical accuracy.</desc><rect width="100%" height="100%" fill="#f8faf9"/><g font-family="Arial,Helvetica,sans-serif" fill="#172e30">']
    def text(x, y, label, size, color="#172e30", weight=400):
        p.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}">{html.escape(str(label))}</text>')
    def rule(x1, y1, x2, y2, color="#a2b8b1", w=2):
        p.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{w}"/>')
    text(38, 50, "RETICLE / SYNTHETIC TIFF COMPARISON", 16, "#27615b", 700)
    text(38, 100, "Same samples. Different spacing.", 38 if not phone else 34, weight=700)
    text(38, 137, "Recorded relative Z positions · common 0–6 µm scale", 19)
    for i, (name, step) in enumerate((("SOURCE", 1.5), ("EXPORT", 3.0))):
        x = 38 if phone else 38 + 575 * i
        y = 185 + 350 * i if phone else 185
        text(x, y, name, 17, "#27615b" if i == 0 else "#9a4232", 700)
        text(x, y + 39, f"{step:g} µm / Z step", 28, weight=700)
        rule(x + 35, y + 75, x + 35, y + 260)
        for n in range(3):
            cy = y + 260 - n * step * 28
            rule(x + 28, cy, x + 42, cy, "#526b65", 2)
            text(x + 52, cy + 6, f"{n * step:g} µm", 18)
            cell = 4
            for row_index, row in enumerate(fixture["pixels"][n]):
                for col, value in enumerate(row):
                    shade = round(value * 255 / 287)
                    p.append(f'<rect x="{x+160+col*cell}" y="{cy-16+row_index*cell}" width="4" height="4" fill="rgb({shade},{shade},{shade})"/>')
            text(x + 225, cy + 6, f"Plane {n}", 17)
    bottom = 910 if phone else 515
    rule(38, bottom - 36, width - 38, bottom - 36)
    text(38, bottom, "Z spacing changed · exit 1", 23, "#9a4232", 700)
    text(38, bottom + 33, "Relative zero is illustrative; thumbnails do not depict thickness.", 17)
    text(38, bottom + 61, "Reticle checks metadata, not pixels or physical calibration.", 17)
    p.append("</g></svg>")
    return "".join(p)


for phone in (False, True):
    name = "calibration-strip-mobile.svg" if phone else "calibration-strip.svg"
    (HERE / name).write_text(figure(phone))
