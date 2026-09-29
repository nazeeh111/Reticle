"""Command line entry point and explicit source/export pairing."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import compare_series, inspect_file
from .report import html_report, pair_status, text_report


def select_series(document, index, label):
    series = document["series"]
    if index is None:
        if len(series) != 1:
            raise ValueError(f"{label} contains {len(series)} series; select one explicitly")
        return series[0]
    if type(index) is not int or index < 0 or index >= len(series):
        raise ValueError(f"{label} series index {index!r} is out of range")
    return series[index]


def compare_pair(pair):
    result = {
        "source": pair.get("display_source", str(pair["source"])),
        "export": pair.get("display_export", str(pair["export"])),
    }
    try:
        source = inspect_file(pair["source"])
        exported = inspect_file(pair["export"])
        s = select_series(source, pair.get("source_series"), "Source")
        x = select_series(exported, pair.get("export_series"), "Export")
        comparison = compare_series(s, x)
        issues = []
        for issue in (
            source["issues"] + exported["issues"] + s["issues"] + x["issues"] + comparison["issues"]
        ):
            if issue not in issues:
                issues.append(issue)
        result.update(
            source_series=s["index"], export_series=x["index"], comparison=comparison, issues=issues
        )
    except (ValueError, OSError) as error:
        message = str(error)
        for key in ("source", "export"):
            path = Path(pair[key])
            spellings = {str(path)}
            try:
                spellings.add(str(path.resolve()))
            except (OSError, RuntimeError):
                pass
            for spelling in spellings:
                message = message.replace(spelling, result[key])
        result["error"] = message
    return result


def exit_status(report):
    return max((pair_status(pair) for pair in report["pairs"]), default=0)


def load_manifest(path):
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Manifest exceeds 1 MiB")
    pairs = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 100:
        raise ValueError("Manifest must contain 1–100 source/export pairs")
    result = []
    for index, pair in enumerate(pairs):
        if not isinstance(pair, dict) or set(pair) - {
            "source",
            "export",
            "source_series",
            "export_series",
        }:
            raise ValueError(f"Manifest pair {index} has unknown fields or is not an object")
        if any(not isinstance(pair.get(k), str) or not pair[k] for k in ("source", "export")):
            raise ValueError(f"Manifest pair {index} needs source and export paths")
        if any(
            type(pair[k]) is not int or pair[k] < 0
            for k in ("source_series", "export_series")
            if k in pair
        ):
            raise ValueError(f"Manifest pair {index} needs nonnegative integer series indices")
        result.append(
            {
                **pair,
                "source": path.parent / pair["source"],
                "export": path.parent / pair["export"],
                "display_source": pair["source"],
                "display_export": pair["export"],
            }
        )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare physical calibration metadata in microscopy TIFF exports."
    )
    parser.add_argument("source", nargs="?")
    parser.add_argument("export", nargs="?")
    parser.add_argument("--source-series", type=int)
    parser.add_argument("--export-series", type=int)
    parser.add_argument(
        "--manifest", help="JSON array of explicit source/export pairs; paths relative to manifest"
    )
    parser.add_argument("--format", choices=("text", "json", "html"), default="text")
    parser.add_argument(
        "--output", type=Path, help="Create a new report file; existing files are never overwritten"
    )
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        if args.manifest:
            if (
                args.source
                or args.export
                or args.source_series is not None
                or args.export_series is not None
            ):
                parser.error(
                    "--manifest cannot be combined with a positional pair or series options"
                )
            pairs = load_manifest(args.manifest)
        else:
            if not args.source or not args.export:
                parser.error("provide source and export paths, or --manifest")
            pairs = [
                {
                    "source": args.source,
                    "export": args.export,
                    "source_series": args.source_series,
                    "export_series": args.export_series,
                }
            ]
        # Preflight destinations before doing any analysis. Exclusive creation below
        # also handles a destination that appears after this check.
        inputs = [Path(pair[key]).resolve() for pair in pairs for key in ("source", "export")]
        if args.manifest:
            inputs.append(Path(args.manifest).resolve())
        if args.output and args.output.resolve() in inputs:
            raise ValueError("Output cannot be an input path")
        if args.output and (args.output.exists() or args.output.is_symlink()):
            raise ValueError("Output already exists; choose a new report path")
        report = {"version": __version__, "pairs": [compare_pair(pair) for pair in pairs]}
        if args.format == "json":
            content = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        elif args.format == "html":
            content = html_report(report)
        else:
            content = text_report(report)
        if args.output:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(content)
        else:
            sys.stdout.write(content)
        return exit_status(report)
    except (ValueError, OSError) as error:
        print(f"reticle: {error}", file=sys.stderr)
        return 2
