"""Batch comparisons and snapshot-bound receipts."""

import hashlib
import os
import stat
import tempfile
from pathlib import Path

from . import __version__
from .core import compare_series, inspect_file
from .report import pair_status

POLICY = "reticle-metadata-2"
LEGACY_POLICY = "reticle-metadata-1"
MAX_INPUT_BYTES = 1024 * 1024 * 1024

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
        source, source_id = inspect_snapshot(pair["source"])
        exported, export_id = inspect_snapshot(pair["export"])
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
            source_series=s["index"], export_series=x["index"],
            source_series_name=s["name"], export_series_name=x["name"],
            comparison=comparison, issues=issues,
            receipt={"source": source_id, "export": export_id}
        )
    except (ValueError, OSError) as error:
        message = "Cannot read input" if isinstance(error, OSError) else str(error)
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




def open_regular(path, limit, label):
    """Open without FIFO waits and admit the opened descriptor, not a path stat."""
    if not hasattr(os, "O_NONBLOCK"):
        raise ValueError("Nonblocking file admission is unavailable")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"{label} must be a regular file")
        if info.st_size > limit:
            raise ValueError(f"{label} exceeds size limit")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def json_equal(left, right):
    """Compare JSON values with exact types, including bool versus number."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(json_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    return left == right


def inspect_snapshot(path):
    """Hash and inspect exactly the same owned snapshot; never decode pixels."""
    original = Path(path).resolve()
    digest = hashlib.sha256()
    size = 0
    with open_regular(original, MAX_INPUT_BYTES, "Input") as source, tempfile.TemporaryDirectory(prefix="reticle-") as directory:
        snapshot = Path(directory) / "input.tif"
        with snapshot.open("xb") as out:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_INPUT_BYTES:
                    raise ValueError("Input exceeds 1 GiB snapshot limit")
                digest.update(chunk)
                out.write(chunk)
        document = inspect_file(snapshot)
    return document, {"path": str(original), "sha256": digest.hexdigest(), "bytes": size}


def compare_batch(pairs, progress=None):
    if not 1 <= len(pairs) <= 100:
        raise ValueError("Batch must contain 1–100 pairs")
    results = []
    for index, pair in enumerate(pairs, 1):
        if progress is not None:
            progress(index, len(pairs), None)
        result = compare_pair(pair)
        results.append(result)
        if progress is not None:
            progress(index, len(pairs), pair_status(result))
    return {"version": __version__, "receipt_policy": POLICY, "pairs": results}


def recheck_report(report):
    if not isinstance(report, dict) or report.get("version") != __version__ or report.get("receipt_policy") not in (POLICY, LEGACY_POLICY):
        raise ValueError("Unsupported or missing receipt policy")
    pairs = report.get("pairs")
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 100:
        raise ValueError("Invalid receipt pairs")
    for saved in pairs:
        try:
            receipt = saved["receipt"]
            pair = {"source": receipt["source"]["path"], "export": receipt["export"]["path"],
                    "source_series": saved["source_series"], "export_series": saved["export_series"],
                    "display_source": saved["source"], "display_export": saved["export"]}
            current = compare_pair(pair)
            # Receipts produced before series names were included remain valid.
            # All original fields are still compared, including byte identities.
            names = ("source_series_name", "export_series_name")
            if report["receipt_policy"] == LEGACY_POLICY:
                if any(key in saved for key in names):
                    raise ValueError("Legacy receipt contains unexpected series names")
                for key in names:
                    current.pop(key, None)
            if not json_equal(current, saved):
                raise ValueError("Receipt differs from current inputs or comparison")
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("Invalid or incomplete receipt") from exc
