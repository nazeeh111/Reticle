"""Self-contained reports: no scripts, external assets, or embedded images."""

import json
from html import escape

VERDICTS = {
    0: "Verified agreement",
    1: "Differences found",
    2: "Cannot establish agreement",
}


def pair_status(pair):
    if "error" in pair:
        return 2
    comparison = pair["comparison"]
    if not comparison["verified"] or any(i["severity"] == "error" for i in pair["issues"]):
        return 2
    if comparison["shape_changes"] or any(
        axis.get("required", True) and axis["status"] != "same" for axis in comparison["axes"]
    ):
        return 1
    return 0


def scale(value):
    if value is None:
        return "Not recorded"
    original = f"{value['value']} {value['unit']}"
    normalized = "" if value["unit"] in ("µm", "μm", "um") else f" ({value['micrometres']} µm)"
    return f"{original}{normalized} · {value['source']}"


def text_report(report):
    lines = ["Reticle · calibration comparison", ""]
    for pair in report["pairs"]:
        lines.append(f"{pair['source']} → {pair['export']}")
        lines.append(f"  Verdict: {VERDICTS[pair_status(pair)]}")
        if "error" in pair:
            lines.append(f"  Cannot compare: {pair['error']}")
            continue
        lines.append(f"  Series {pair['source_series']} → {pair['export_series']}")
        comparison = pair["comparison"]
        for axis in comparison["axes"]:
            lines.append(
                f"  {axis['axis']}: {axis['status'] if axis.get('required', True) else 'not applicable'} | {scale(axis['source'])} → {scale(axis['export'])}"
            )
        for change in comparison["shape_changes"]:
            lines.append(f"  Dimensions: {json.dumps(change, ensure_ascii=False)}")
        if not comparison["verified"]:
            lines.append("  Mapping is unverified; agreement is not established.")
        for issue in pair["issues"]:
            lines.append(f"  {issue['severity']}: {issue['code']} · {issue['message']}")
        lines.append("")
    lines.append("Metadata only. Pixel equality and instrument accuracy are not checked.")
    return "\n".join(lines) + "\n"


def html_report(report):
    def e(value):
        return escape(str(value), quote=True)

    sections = []
    for index, pair in enumerate(report["pairs"], 1):
        title = f"<h2><span>{index:02}</span> {e(pair['source'])} <b>→</b> {e(pair['export'])}</h2>"
        status = pair_status(pair)
        verdict_class = {0: "verified", 1: "different", 2: "unverified"}[status]
        verdict = f'<p class="verdict {verdict_class}">{VERDICTS[status]}</p>'
        if "error" in pair:
            sections.append(
                f'<section>{title}{verdict}<p class="error">Cannot compare: {e(pair["error"])}</p></section>'
            )
            continue
        c = pair["comparison"]
        rows = "".join(
            f'<tr><th scope="row">{e(a["axis"])}</th><td>{e(scale(a["source"]))}</td>'
            f'<td>{e(scale(a["export"]))}</td><td class="{e(a["status"])}">{e(a["status"] if a.get("required", True) else "not applicable")}</td></tr>'
            for a in c["axes"]
        )
        notes = "".join(f"<li>{e(i['message'])}</li>" for i in pair["issues"])
        shape = "".join(
            f"<li>Dimensions: {e(json.dumps(change, ensure_ascii=False))}</li>"
            for change in c["shape_changes"]
        )
        mapping = "Plane mapping checked" if c["verified"] else "Plane mapping unverified"
        sections.append(f"""<section>{title}{verdict}<p>Series {e(pair["source_series"])} → {e(pair["export_series"])} · {mapping}</p>
<div class="scroll"><table><thead><tr><th>Axis</th><th>Source spacing</th><th>Export spacing</th><th>Finding</th></tr></thead><tbody>{rows}</tbody></table></div>
<ul>{shape}{notes}</ul></section>""")
    return (
        """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Reticle · calibration comparison</title><style>
:root{color-scheme:light;font-family:system-ui,sans-serif;color:#222c31;background:#f4f2ed}body{max-width:1100px;margin:auto;padding:44px 28px}header{border-top:5px solid #245b57;padding-top:22px;margin-bottom:38px}h1{font-size:36px;letter-spacing:-1.5px;margin:0 0 10px}header p{max-width:72ch;line-height:1.6}section{border-top:1px solid #a5afaa;padding:20px 0;margin:20px 0}h2{font-size:19px;overflow-wrap:anywhere}h2 span{font:14px ui-monospace,monospace;color:#52605a;margin-right:14px}h2 b{font-weight:400;color:#64746b}.verdict{display:inline-block;margin:2px 0 8px;padding:7px 12px;border-radius:4px;font-weight:700}.verdict.verified{background:#dcece5;color:#205445}.verdict.different{background:#fae3db;color:#922f21}.verdict.unverified{background:#fff0ce;color:#694b00}p,li{font-size:14px;line-height:1.6}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;text-align:left;font-size:14px}th,td{padding:14px 12px;border-bottom:1px solid #d7d9d2;vertical-align:top}thead{background:#e6e9e2}tbody th{font:600 18px ui-monospace,monospace}.same{color:#245b57}.changed,.lost,.error{color:#9c3526}.gained,.unknown{color:#755500}ul{padding-left:22px}footer{border-top:1px solid #a5afaa;padding-top:15px;font-size:12px;color:#52605a}@media print{body{padding:0;background:white}.scroll{overflow:visible}section{break-inside:avoid}}
</style></head><body><header><h1>Reticle</h1><p>Physical calibration in source and exported TIFF files. “Same” means the recorded values agree after unit conversion. It does not establish instrument accuracy or pixel equality.</p></header>"""
        + "".join(sections)
        + f"<footer>Reticle {e(report['version'])} · Read-only metadata comparison · No image pixels included</footer></body></html>\n"
    )
