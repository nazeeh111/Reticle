"""Read-only calibration inspection for scalar TIFF and single-file OME-TIFF."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

import tifffile
from defusedxml import ElementTree as ET

OME_NS = "http://www.openmicroscopy.org/Schemas/OME/2016-06"
MAX_XML_BYTES = 4_000_000
MAX_MAPPED_PLANES = 1_000_000
MAX_TIFFDATA_ELEMENTS = 10_000
MAX_MAPPING_STEPS = 100_000
RELATIVE_TOLERANCE = Decimal("1e-9")
MAX_DECIMAL_TEXT = 128
MAX_ABS_DECIMAL_EXPONENT = 100
MICROMETRES_PER_UNIT = {
    "pm": Decimal("0.000001"),
    "nm": Decimal("0.001"),
    "µm": Decimal(1),
    "μm": Decimal(1),
    "um": Decimal(1),
    "mm": Decimal(1000),
    "cm": Decimal(10000),
    "dm": Decimal(100000),
    "m": Decimal(1000000),
    "km": Decimal(1000000000),
    "Å": Decimal("0.0001"),
}
OME_SCALAR_DTYPES = {
    "int8": ("i", 1),
    "uint8": ("u", 1),
    "int16": ("i", 2),
    "uint16": ("u", 2),
    "int32": ("i", 4),
    "uint32": ("u", 4),
    "int64": ("i", 8),
    "uint64": ("u", 8),
    "float": ("f", 4),
    "double": ("f", 8),
}


def _issue(code: str, message: str, severity: str = "error", axis: str | None = None) -> dict:
    issue = {"code": code, "severity": severity, "message": message}
    if axis is not None:
        issue["axis"] = axis
    return issue


def _append_issue_once(issues: list[dict], code: str, message: str) -> None:
    if not any(issue["code"] == code for issue in issues):
        issues.append(_issue(code, message))


def _positive_decimal(raw: str, description: str) -> Decimal:
    if len(str(raw)) > MAX_DECIMAL_TEXT:
        raise ValueError(f"{description} numeric text exceeds {MAX_DECIMAL_TEXT} characters")
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid {description}: {raw!r}") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{description} must be finite and positive: {raw!r}")
    if abs(value.adjusted()) > MAX_ABS_DECIMAL_EXPONENT:
        raise ValueError(f"{description} magnitude is outside the supported range: {raw!r}")
    return value


def _nonnegative_int(raw: str, description: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {description}: {raw!r}") from exc
    if str(value) != str(raw) or value < 0:
        raise ValueError(f"Invalid {description}: {raw!r}")
    return value


def _calibration(
    value_text: str | None, unit: str | None, source: str, axis: str, issues: list[dict]
) -> dict | None:
    if value_text is None:
        if unit is not None:
            issues.append(_issue("orphan_unit", f"{axis} has a unit but no size value", axis=axis))
        return None
    value = _positive_decimal(value_text, f"PhysicalSize{axis}")
    unit = unit if unit is not None else "µm"  # OME schema default.
    factor = MICROMETRES_PER_UNIT.get(unit)
    if factor is None:
        issues.append(_issue("unsupported_unit", f"Unsupported {axis} unit {unit!r}", axis=axis))
        return None
    with localcontext() as context:
        context.prec = max(50, len(value.as_tuple().digits) + len(factor.as_tuple().digits) + 2)
        converted = value * factor
    if not converted.is_finite() or converted <= 0:
        raise ValueError(f"PhysicalSize{axis} cannot be normalized safely")
    return {"value": value_text, "unit": unit, "micrometres": str(converted), "source": source}


def _scalar_page_issue(page, expected_xy: tuple[int, int] | None = None) -> dict | None:
    if page.tags.get("SubIFDs") is not None or page.is_subifd:
        return _issue("pyramid", "SubIFD pyramid levels are unsupported")
    orientation = page.tags.get("Orientation")
    if orientation is not None and int(orientation.value) != 1:
        return _issue("orientation", "TIFF orientation other than top-left is unsupported")
    if page.samplesperpixel != 1 or int(page.photometric) not in (0, 1):
        return _issue("non_scalar", "RGB, palette, and interleaved pages are unsupported")
    if expected_xy is not None and (page.imagewidth, page.imagelength) != expected_xy:
        return _issue("plane_shape", "Mapped TIFF planes have inconsistent X/Y dimensions")
    return None


def _ome_series(tiff, root) -> tuple[list[dict], list[dict]]:
    global_issues: list[dict] = []
    images = root.findall(f"{{{OME_NS}}}Image")
    if not images:
        raise ValueError("OME-XML contains no Image elements")
    ifd_owners: dict[int, int] = {}
    entries_remaining = MAX_TIFFDATA_ELEMENTS
    steps_remaining = MAX_MAPPING_STEPS
    series_list: list[dict] = []
    for index, image in enumerate(images):
        issues: list[dict] = []
        pixels = image.find(f"{{{OME_NS}}}Pixels")
        if pixels is None:
            raise ValueError(f"OME Image {index} contains no Pixels element")
        shape = {}
        for axis in "XYZCT":
            size = _nonnegative_int(pixels.get(f"Size{axis}"), f"Image {index} Size{axis}")
            if size == 0:
                raise ValueError(f"Image {index} Size{axis} must be positive")
            shape[axis] = size
        dimension_order = pixels.get("DimensionOrder")
        if (
            dimension_order is None
            or not dimension_order.startswith("XY")
            or set(dimension_order) != set("XYZCT")
            or len(dimension_order) != 5
        ):
            raise ValueError(f"Image {index} has invalid DimensionOrder {dimension_order!r}")
        calibration = {
            axis: _calibration(
                pixels.get(f"PhysicalSize{axis}"),
                pixels.get(f"PhysicalSize{axis}Unit"),
                "OME PhysicalSize",
                axis,
                issues,
            )
            for axis in "XYZ"
        }
        pixel_type = pixels.get("Type")
        expected_dtype = OME_SCALAR_DTYPES.get(pixel_type)
        if expected_dtype is None:
            issues.append(
                _issue("unsupported_pixel_type", f"OME Pixels Type {pixel_type!r} is unsupported")
            )
        if pixels.get("Interleaved", "false").lower() != "false":
            issues.append(_issue("interleaved", "Interleaved OME pixels are unsupported"))
        channels = pixels.findall(f"{{{OME_NS}}}Channel")
        if any(channel.get("SamplesPerPixel", "1") != "1" for channel in channels):
            issues.append(_issue("interleaved", "Multi-sample OME channels are unsupported"))
        tiff_data = pixels.findall(f"{{{OME_NS}}}TiffData")
        if not tiff_data:
            issues.append(_issue("missing_tiffdata", "OME Pixels contains no TiffData mapping"))
        if len(tiff_data) > entries_remaining:
            issues.append(
                _issue("mapping_too_large", "OME TiffData element count exceeds inspection limit")
            )
            tiff_data = []
        else:
            entries_remaining -= len(tiff_data)
        total = shape["Z"] * shape["C"] * shape["T"]
        if total > MAX_MAPPED_PLANES:
            issues.append(_issue("mapping_too_large", "OME plane mapping exceeds inspection limit"))
        coords_to_ifd: dict[int, int] = {}
        local_ifds: set[int] = set()
        if total <= MAX_MAPPED_PLANES:
            for entry in tiff_data:
                if entry.find(f"{{{OME_NS}}}UUID") is not None:
                    issues.append(
                        _issue("external_reference", "External OME file references are unsupported")
                    )
                    continue
                explicit_ifd = entry.get("IFD") is not None
                ifd = _nonnegative_int(entry.get("IFD", "0"), "TiffData IFD")
                count = _nonnegative_int(
                    entry.get("PlaneCount", "1" if explicit_ifd else str(len(tiff.pages))),
                    "TiffData PlaneCount",
                )
                first = {
                    axis: _nonnegative_int(entry.get(f"First{axis}", "0"), f"TiffData First{axis}")
                    for axis in "ZTC"
                }
                if any(first[axis] >= shape[axis] for axis in "ZTC"):
                    issues.append(
                        _issue(
                            "mapping_out_of_bounds",
                            "TiffData first coordinate exceeds Pixels dimensions",
                        )
                    )
                    continue
                start = 0
                stride = 1
                for axis in dimension_order[2:]:
                    start += first[axis] * stride
                    stride *= shape[axis]
                # A bare TiffData maps as many planes as fit in the OME image;
                # trailing IFDs are expressly ignored by the OME-TIFF spec.
                if entry.get("PlaneCount") is None and not explicit_ifd:
                    count = min(count, total - start)
                if count > MAX_MAPPED_PLANES:
                    issues.append(
                        _issue("mapping_too_large", "TiffData PlaneCount exceeds inspection limit")
                    )
                    continue
                if count > steps_remaining:
                    _append_issue_once(
                        issues,
                        "mapping_too_large",
                        "OME TiffData mapping exceeds inspection work limit",
                    )
                    break
                steps_remaining -= count
                for offset in range(count):
                    coord = start + offset
                    page_index = ifd + offset
                    if coord >= total or page_index >= len(tiff.pages):
                        issues.append(
                            _issue(
                                "mapping_out_of_bounds",
                                "TiffData refers beyond the OME dimensions or TIFF IFDs",
                            )
                        )
                        break
                    if page_index in ifd_owners:
                        prior = series_list[ifd_owners[page_index]]
                        _append_issue_once(
                            prior["issues"],
                            "duplicate_mapping",
                            f"IFD {page_index} is reused by Image {index}",
                        )
                        _append_issue_once(
                            issues,
                            "duplicate_mapping",
                            f"IFD {page_index} is reused by Image {index}",
                        )
                        break
                    if coord in coords_to_ifd or page_index in local_ifds:
                        _append_issue_once(
                            issues,
                            "duplicate_mapping",
                            "TiffData assigns a coordinate or IFD more than once",
                        )
                        break
                    coords_to_ifd[coord] = page_index
                    local_ifds.add(page_index)
            if len(coords_to_ifd) != total:
                issues.append(
                    _issue(
                        "missing_mapping",
                        f"Only {len(coords_to_ifd)} of {total} OME planes are mapped",
                    )
                )
        for page_index in local_ifds:
            page = tiff.pages[page_index]
            problem = _scalar_page_issue(page, (shape["X"], shape["Y"]))
            if problem is not None and problem not in issues:
                issues.append(problem)
            dtype = page.dtype
            if expected_dtype is not None and (
                dtype is None or (dtype.kind, dtype.itemsize) != expected_dtype
            ):
                _append_issue_once(
                    issues,
                    "pixel_type_mismatch",
                    f"OME Pixels Type {pixel_type!r} does not match TIFF IFD {page_index} type {dtype}",
                )
        for page_index in local_ifds:
            ifd_owners[page_index] = index
        series_list.append(
            {
                "index": index,
                "name": image.get("Name") or image.get("ID") or f"Image {index}",
                "shape": shape,
                "calibration": calibration,
                "verified_mapping": not any(i["severity"] == "error" for i in issues),
                "issues": issues,
            }
        )
    for series in series_list:
        series["verified_mapping"] = not any(i["severity"] == "error" for i in series["issues"])
    return series_list, global_issues


def _resolution_calibration(pages, axis: str, issues: list[dict]) -> dict | None:
    tag_name = f"{axis}Resolution"
    values = []
    for page in pages:
        unit_tag = page.tags.get("ResolutionUnit")
        resolution_tag = page.tags.get(tag_name)
        unit_code = int(unit_tag.value) if unit_tag is not None else 2  # TIFF 6 default: inch.
        if unit_code == 1 or resolution_tag is None:
            values.append(None)
            continue
        if unit_code not in (2, 3):
            issues.append(
                _issue(
                    "unsupported_unit", f"Unsupported TIFF resolution unit {unit_code}", axis=axis
                )
            )
            return None
        numerator, denominator = resolution_tag.value
        numerator = _positive_decimal(str(numerator), tag_name)
        denominator = _positive_decimal(str(denominator), tag_name)
        with localcontext() as context:
            context.prec = 50
            values.append(
                (Decimal(25400) if unit_code == 2 else Decimal(10000)) * denominator / numerator
            )
    if len(set(values)) != 1:
        issues.append(
            _issue("inconsistent_resolution", f"{tag_name} differs between TIFF pages", axis=axis)
        )
        return None
    if values[0] is None:
        return None
    unit_tag = pages[0].tags.get("ResolutionUnit")
    return {
        "value": str(pages[0].tags[tag_name].value[0])
        + "/"
        + str(pages[0].tags[tag_name].value[1]),
        "unit": "pixels/inch" if unit_tag is None or int(unit_tag.value) == 2 else "pixels/cm",
        "micrometres": str(values[0]),
        "source": f"TIFF {tag_name}/ResolutionUnit"
        if unit_tag is not None
        else f"TIFF {tag_name}/default inch unit",
    }


def _plain_series(tiff) -> tuple[list[dict], list[dict]]:
    issues: list[dict] = []
    if tiff.is_imagej:
        issues.append(_issue("imagej", "ImageJ-specific dimensions are unsupported"))
    pages = list(tiff.pages)
    if not pages:
        raise ValueError("TIFF contains no image pages")
    xy = (pages[0].imagewidth, pages[0].imagelength)
    for page in pages:
        problem = _scalar_page_issue(page, xy)
        if problem is not None and problem not in issues:
            issues.append(problem)
    if len(pages) > 1:
        issues.append(
            _issue(
                "unlabeled_pages", "Ordinary TIFF pages have no verified Z/C/T labels", "warning"
            )
        )
    calibration = {axis: _resolution_calibration(pages, axis, issues) for axis in "XY"}
    calibration["Z"] = None
    shape = {"X": xy[0], "Y": xy[1]}
    if len(pages) == 1:
        # This is a local one-plane TIFF layout, not a claim about an
        # acquisition or external file set absent from the TIFF itself.
        shape.update({"Z": 1, "C": 1, "T": 1})
        issues.append(
            _issue(
                "local_one_plane", "Z/C/T=1 describes this file's one TIFF plane only", "warning"
            )
        )
    series = {
        "index": 0,
        "name": "TIFF pages",
        "shape": shape,
        "calibration": calibration,
        "verified_mapping": len(pages) == 1 and not any(i["severity"] == "error" for i in issues),
        "issues": issues,
    }
    return [series], []


def inspect_file(path) -> dict:
    """Inspect TIFF metadata and validate supported plane mappings without decoding pixels."""
    file_path = Path(path)
    try:
        with tifffile.TiffFile(file_path, _multifile=False) as tiff:
            if not tiff.pages:
                raise ValueError("TIFF contains no image pages")
            description = tiff.pages[0].description or ""
            if tiff.is_ome or "<OME" in description or ":OME" in description:
                if len(description.encode("utf-8")) > MAX_XML_BYTES:
                    raise ValueError("OME-XML metadata exceeds 4 MB inspection limit")
                try:
                    root = ET.fromstring(description)
                except Exception as exc:
                    raise ValueError(f"Invalid OME-XML: {exc}") from exc
                if root.tag != f"{{{OME_NS}}}OME":
                    raise ValueError("Unsupported OME-XML namespace")
                series, issues = _ome_series(tiff, root)
                format_name = "OME-TIFF"
            else:
                series, issues = _plain_series(tiff)
                format_name = "TIFF"
            return {
                "basename": file_path.name,
                "format": format_name,
                "series": series,
                "issues": issues,
            }
    except ValueError:
        raise
    except (OSError, tifffile.TiffFileError, TypeError, KeyError) as exc:
        raise ValueError(f"Cannot inspect {file_path.name}: {exc}") from exc


def compare_series(source_series: dict, export_series: dict) -> dict:
    """Compare declared physical sizes and known dimensions of two selected series."""
    axes = []
    for axis in "XYZ":
        source = source_series["calibration"].get(axis)
        export = export_series["calibration"].get(axis)
        unresolved = any(
            issue.get("axis") == axis
            and issue.get("code") in {"unsupported_unit", "orphan_unit", "inconsistent_resolution"}
            for series in (source_series, export_series)
            for issue in series.get("issues", [])
        )
        required = (
            axis in "XY"
            or source is not None
            or export is not None
            or any(
                series.get("shape", {}).get("Z") != 1 for series in (source_series, export_series)
            )
        )
        if unresolved or source is None and export is None:
            status = "unknown"
        elif source is None:
            status = "gained"
        elif export is None:
            status = "lost"
        else:
            first = Decimal(source["micrometres"])
            second = Decimal(export["micrometres"])
            status = (
                "same"
                if abs(first - second) <= RELATIVE_TOLERANCE * max(abs(first), abs(second))
                else "changed"
            )
        axes.append(
            {
                "axis": axis,
                "status": status,
                "required": required,
                "source": source,
                "export": export,
            }
        )
    source_shape = source_series.get("shape", {})
    export_shape = export_series.get("shape", {})
    shape_changes = [
        {"axis": axis, "source": source_shape[axis], "export": export_shape[axis]}
        for axis in "XYZCT"
        if axis in source_shape
        and axis in export_shape
        and source_shape[axis] != export_shape[axis]
    ]
    issues = list(source_series.get("issues", [])) + list(export_series.get("issues", []))
    verified = bool(
        source_series.get("verified_mapping")
        and export_series.get("verified_mapping")
        and not any(i["severity"] == "error" for i in issues)
    )
    if not verified:
        issues.append(
            _issue(
                "unverified_comparison",
                "At least one series mapping or layout is unverified",
                "warning",
            )
        )
    return {"axes": axes, "shape_changes": shape_changes, "verified": verified, "issues": issues}
