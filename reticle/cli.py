"""Command line entry point and explicit source/export pairing."""

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from . import __version__
from .batch import compare_batch, compare_pair, exit_status, select_series, recheck_report, open_regular
from .report import html_report, pair_status, text_report


def _read_bytes(path, limit, label):
    with open_regular(path, limit, label) as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"{label} exceeds size limit")
    return raw


def _write_report(path, content):
    """Publish one complete report without replacing another writer's output."""
    stage = path.with_name(f".reticle-{uuid4().hex}.tmp")
    descriptor = None
    published = False
    try:
        descriptor = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        try:
            stream = os.fdopen(descriptor, "w", encoding="utf-8")
        except BaseException:
            os.close(descriptor)
            raise
        with stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(stage, path)
        published = True
    finally:
        if descriptor is not None:
            try:
                stage.unlink()
            except OSError as error:
                outcome = f"Report saved at {path}" if published else "Report was not published"
                print(f"reticle: {outcome}; staging cleanup failed at {stage}: {error}", file=sys.stderr)


def load_manifest(path):
    path = Path(path)
    pairs = json.loads(_read_bytes(path, 1024 * 1024, "Manifest").decode("utf-8"))
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
        description="Compare microscopy TIFF calibration metadata, not pixel equality or physical accuracy.",
        epilog="Exit 0: verified agreement; 1: calibration/dimension difference or required value missing; 2: input or mapping could not be checked. JSON receipts contain absolute input paths. Recheck only trusted reports."
    )
    parser.add_argument("source", nargs="?", help="Source TIFF")
    parser.add_argument("export", nargs="?", help="Export TIFF")
    parser.add_argument("--source-series", type=int, help="Zero-based source series index")
    parser.add_argument("--export-series", type=int, help="Zero-based export series index")
    parser.add_argument(
        "--manifest", help="JSON array of explicit source/export pairs; paths relative to manifest"
    )
    parser.add_argument("--format", choices=("text", "json", "html"), default="text")
    parser.add_argument(
        "--output", type=Path, help="Create a new report file; existing files are never overwritten"
    )
    parser.add_argument("--recheck", type=Path, help="Reinspect paths in a trusted JSON receipt; retain its aggregate exit status")
    parser.add_argument("--progress", action="store_true", help="Show pair-level progress on stderr")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        if args.recheck:
            if args.source or args.export or args.manifest or args.source_series is not None or args.export_series is not None or args.output or args.format != "text" or args.progress:
                parser.error("--recheck cannot be combined with other inputs or output options")
            receipt_bytes = _read_bytes(args.recheck, 4 * 1024 * 1024, "Receipt")
            report = json.loads(receipt_bytes)
            recheck_report(report)
            status = exit_status(report)
            print(f"Receipt matches current inputs and policy; aggregate exit {status}.")
            return status
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
        def progress(index, total, status):
            message = "inspecting" if status is None else ("agreement", "differences", "unverified")[status]
            print(f"reticle: pair {index}/{total}: {message}", file=sys.stderr, flush=True)

        report = compare_batch(pairs, progress=progress if args.progress else None)
        if args.format == "json":
            content = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        elif args.format == "html":
            content = html_report(report)
        else:
            content = text_report(report)
        if args.output:
            _write_report(args.output, content)
            print(f"Report written: {args.output}; aggregate exit {exit_status(report)}.", file=sys.stderr)
        else:
            sys.stdout.write(content)
        return exit_status(report)
    except (ValueError, OSError) as error:
        print(f"reticle: {error}", file=sys.stderr)
        return 2
