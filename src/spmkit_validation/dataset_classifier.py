#!/usr/bin/env python3
"""
Non-destructive classifier for SPM-Kit / Fathom validation datasets.

What it does
------------
- Recursively inventories every file below a dataset root.
- Assigns conservative file roles from extension, filename, and light text inspection.
- Classifies each top-level dataset folder by likely validation utility.
- Computes SHA-256 hashes and detects exact duplicate files.
- Detects exact duplicate dataset folders from normalized file manifests.
- Optionally probes readable scientific files with `spmkit info`.
- Writes CSV, JSONL, and Markdown reports without modifying source data.

Python: 3.11+
Dependencies: standard library only.

Example
-------
spmkit-validation-classify \
  "<dataset-root>/DATA PARA VALIDACION | DATA FOR VALIDATION" \
  --output "<triage-output>" \
  --probe-spmkit \
  --symlinks
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RAW_EXTENSIONS = {
    ".nid", ".nhf", ".gwy", ".spm", ".sur", ".sdf", ".opd", ".opdx",
    ".ibw", ".jpk", ".jpk-force", ".001", ".002", ".003", ".004",
    ".005", ".mdt", ".sxm", ".sm4", ".bcrf", ".lext",
}

MATRIX_EXTENSIONS = {
    ".csv", ".tsv", ".txt", ".xyz", ".dat", ".asc", ".nc",
    ".npy", ".npz", ".mat", ".h5", ".hdf5", ".tif", ".tiff",
}

REFERENCE_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".xml", ".yaml", ".yml"}
DOCUMENT_EXTENSIONS = {".pdf", ".md", ".rst", ".doc", ".docx", ".tex", ".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".svg"}
ARCHIVE_EXTENSIONS = {
    ".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2", ".txz"
}
CODE_EXTENSIONS = {
    ".py", ".ipynb", ".m", ".r", ".jl", ".cpp", ".c", ".h", ".hpp", ".sh", ".ps1"
}
METADATA_EXTENSIONS = {".json", ".jsonld", ".xml", ".yaml", ".yml", ".ini", ".toml"}

SUPPORTED_SPMKIT_PROBE_EXTENSIONS = {
    ".nid", ".nhf", ".gwy", ".jpk", ".jpk-force", ".ibw", ".001", ".002"
}

ROLE_ORDER = [
    "raw_instrument",
    "height_matrix",
    "processed_topography",
    "reference_metrics",
    "reference_psd",
    "reference_acf",
    "metadata",
    "provenance",
    "publication",
    "code",
    "image_preview",
    "archive",
    "unknown",
    "rejected",
]

NAME_PATTERNS = {
    "reference_psd": (
        "psd", "power spectral density", "power_spectral_density",
        "spectrum", "spectral density",
    ),
    "reference_acf": (
        "acf", "autocorrelation", "auto-correlation", "correlation function",
        "correlation_length",
    ),
    "reference_metrics": (
        "roughness", "roughness_metrics", "surface_parameters",
        "measurement_statistics", "measurement_results",
    ),
    "height_matrix": (
        "height", "topography", "surface", "profile", "xyz", "matrix", "map",
    ),
    "metadata": (
        "metadata", "meta", "manifest", "dataset", "record", "description",
        "instrument", "parameters", "settings",
    ),
    "provenance": (
        "license", "licence", "citation", "doi", "provenance", "readme",
        "authors", "source",
    ),
    "publication": (
        "paper", "article", "publication", "supplement", "manuscript", "thesis",
    ),
    "processed_topography": (
        "processed", "filtered", "leveled", "levelled", "detrended", "flattened",
    ),
}

TEXT_KEYWORDS = {
    "afm": ("atomic force microscopy", "afm"),
    "spm": ("scanning probe microscopy", "spm"),
    "profilometry": ("profilometer", "profilometry", "profilometric"),
    "interferometry": ("interferometer", "interferometry", "white light"),
    "roughness": ("roughness", " sa ", " sq ", " sz ", "ssk", "sku", "rms"),
    "psd": ("power spectral density", " psd "),
    "acf": ("autocorrelation", "auto-correlation", " acf "),
    "units": (" nm", " µm", " um", " mm", " meter", " metre", "height unit"),
    "dimensions": ("scan size", "pixel size", "resolution", "width", "height"),
    "doi": ("doi.org/", "doi:"),
    "license": ("license", "licence", "creative commons", "cc-by", "mit license"),
    "tip_radius": ("tip radius", "probe radius", "tip diameter"),
    "repeated": ("repeat", "replicate", "measurement 1", "measurement 2"),
    "multiscale": ("multiscale", "multi-scale", "different scale", "scan size"),
}


@dataclass
class FileRecord:
    dataset_id: str
    dataset_path: str
    relative_path: str
    absolute_path: str
    name: str
    extension: str
    size_bytes: int
    modified_utc: str
    mime_type: str
    role: str
    role_confidence: str
    readable: bool
    is_archive: bool
    sha256: str
    quick_fingerprint: str
    numeric_text_likelihood: str
    detected_keywords: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class DatasetRecord:
    dataset_id: str
    local_path: str
    total_size_bytes: int
    file_count: int
    primary_utility: str
    secondary_tags: list[str]
    triage_score: int
    priority: str
    raw_available: bool
    height_matrix_available: bool
    reference_roughness: bool
    reference_psd: bool
    reference_acf: bool
    units_known: bool
    dimensions_known: bool
    instrument_known: bool
    has_doi: bool
    has_license: bool
    spmkit_readable: bool
    spmkit_probe_successes: int
    spmkit_probe_failures: int
    duplicate_group: str
    manual_review_required: bool
    notes: str


@dataclass
class ProbeResult:
    dataset_id: str
    relative_path: str
    command: str
    exit_code: int | None
    timed_out: bool
    runtime_seconds: float
    success: bool
    stdout: str
    stderr: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify SPM/AFM validation datasets without modifying originals."
    )
    parser.add_argument(
        "root",
        type=Path,
        help="Root directory whose immediate children are dataset folders/files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory. Default: <root parent>/validation/triage",
    )
    parser.add_argument(
        "--probe-spmkit",
        action="store_true",
        help="Run `spmkit info` on supported files and record the result.",
    )
    parser.add_argument(
        "--spmkit-command",
        default="spmkit",
        help="SPM-Kit CLI executable. Default: spmkit",
    )
    parser.add_argument(
        "--probe-timeout",
        type=int,
        default=45,
        help="Timeout per SPM-Kit probe in seconds. Default: 45",
    )
    parser.add_argument(
        "--symlinks",
        action="store_true",
        help="Create non-destructive organized symlink views.",
    )
    parser.add_argument(
        "--max-text-inspection-bytes",
        type=int,
        default=2_000_000,
        help="Maximum bytes read for light text inspection. Default: 2 MB",
    )
    parser.add_argument(
        "--full-hash-limit-gb",
        type=float,
        default=2.0,
        help="Full SHA-256 limit per file. Larger files use a sampled fingerprint. Default: 2 GiB",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(2, min(8, os.cpu_count() or 4)),
        help="Reserved for future parallel hashing. Current implementation is sequential.",
    )
    return parser.parse_args()


def utc_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def safe_read_text(path: Path, max_bytes: int) -> str:
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes)
        return raw.decode("utf-8", errors="ignore")
    except (OSError, UnicodeError):
        return ""


def normalized_extension(path: Path) -> str:
    lower = path.name.lower()
    for suffix in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if lower.endswith(suffix):
            return suffix
    return path.suffix.lower()


def quick_fingerprint(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash size + first and last chunk. Useful for huge files."""
    try:
        size = path.stat().st_size
        digest = hashlib.sha256()
        digest.update(str(size).encode("ascii"))
        with path.open("rb") as handle:
            digest.update(handle.read(chunk_size))
            if size > chunk_size:
                handle.seek(max(0, size - chunk_size))
                digest.update(handle.read(chunk_size))
        return digest.hexdigest()
    except OSError:
        return ""


def full_sha256(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def looks_numeric_text(text: str) -> tuple[str, dict[str, Any]]:
    if not text.strip():
        return "no", {}

    lines = [line.strip() for line in text.splitlines()[:300] if line.strip()]
    if not lines:
        return "no", {}

    numeric_tokens = 0
    total_tokens = 0
    numeric_rows = 0
    consistent_widths: Counter[int] = Counter()

    number_re = re.compile(
        r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
    )

    for line in lines:
        if line.startswith(("#", "%", ";")):
            continue
        tokens = [t for t in re.split(r"[\s,;\t]+", line) if t]
        if not tokens:
            continue
        row_numeric = sum(bool(number_re.match(token)) for token in tokens)
        numeric_tokens += row_numeric
        total_tokens += len(tokens)
        if row_numeric >= max(2, int(len(tokens) * 0.7)):
            numeric_rows += 1
            consistent_widths[len(tokens)] += 1

    if total_tokens == 0:
        return "no", {}

    ratio = numeric_tokens / total_tokens
    common_width, common_count = (
        consistent_widths.most_common(1)[0] if consistent_widths else (0, 0)
    )

    if ratio >= 0.85 and numeric_rows >= 5 and common_width >= 2:
        likelihood = "high"
    elif ratio >= 0.55 and numeric_rows >= 3:
        likelihood = "medium"
    else:
        likelihood = "low"

    return likelihood, {
        "numeric_ratio": round(ratio, 4),
        "numeric_rows": numeric_rows,
        "common_columns": common_width,
        "common_column_rows": common_count,
    }


def detect_keywords(text: str, filename: str) -> list[str]:
    haystack = f" {filename.lower()} {text.lower()} "
    hits: list[str] = []
    for tag, keywords in TEXT_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            hits.append(tag)
    return sorted(set(hits))


def classify_file(path: Path, text: str, numeric_likelihood: str) -> tuple[str, str, str]:
    ext = normalized_extension(path)
    name = path.name.lower()
    notes: list[str] = []

    if not path.is_file():
        return "rejected", "high", "Not a regular file"

    if ext in ARCHIVE_EXTENSIONS:
        return "archive", "high", ""

    if ext in RAW_EXTENSIONS:
        return "raw_instrument", "high", ""

    for role in (
        "reference_psd",
        "reference_acf",
        "reference_metrics",
        "processed_topography",
        "metadata",
        "provenance",
        "publication",
        "height_matrix",
    ):
        if any(token in name for token in NAME_PATTERNS[role]):
            if role == "height_matrix" and ext not in MATRIX_EXTENSIONS:
                continue
            if role in {"reference_psd", "reference_acf", "reference_metrics"} and ext not in (
                REFERENCE_EXTENSIONS | MATRIX_EXTENSIONS | DOCUMENT_EXTENSIONS
            ):
                continue
            return role, "medium", "Classified from filename"

    if ext in CODE_EXTENSIONS:
        return "code", "high", ""

    if ext in DOCUMENT_EXTENSIONS:
        return "publication", "medium", ""

    if ext in IMAGE_EXTENSIONS:
        return "image_preview", "high", ""

    if ext in METADATA_EXTENSIONS:
        return "metadata", "medium", ""

    if ext in MATRIX_EXTENSIONS:
        if numeric_likelihood == "high":
            return "height_matrix", "medium", "Dense numeric text/table"
        if ext in {
            ".npy", ".npz", ".mat", ".h5", ".hdf5",
            ".tif", ".tiff", ".nc",
        }:
            return (
                "height_matrix",
                "low",
                "Binary scientific container; contents not deeply inspected",
            )
        return "unknown", "low", "Matrix-like extension but numerical structure unclear"

    if text:
        lower = text.lower()
        if "power spectral density" in lower or re.search(r"\bpsd\b", lower):
            return "reference_psd", "medium", "Classified from text content"
        if "autocorrelation" in lower or re.search(r"\bacf\b", lower):
            return "reference_acf", "medium", "Classified from text content"
        metric_value = re.search(
            r"(?im)^\\s*(?:sa|sq|sz|ssk|sku|rms)"
            r"\\s*(?:\\([^)]*\\))?\\s*[:=,\\t]\\s*"
            r"[-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)"
            r"(?:[eE][-+]?\\d+)?",
            text,
        )

        if metric_value:
            return (
                "reference_metrics",
                "high",
                "Metric label accompanied by a numeric value",
            )

    return "unknown", "low", "; ".join(notes)


def dataset_entries(root: Path) -> list[Path]:
    return sorted(
        (entry for entry in root.iterdir() if not entry.name.startswith(".")),
        key=lambda p: p.name.lower(),
    )


def iter_dataset_files(dataset_path: Path) -> Iterator[Path]:
    if dataset_path.is_file():
        yield dataset_path
        return

    for path in sorted(dataset_path.rglob("*")):
        try:
            if path.is_symlink():
                continue
            if path.is_file():
                yield path
        except OSError:
            continue


def dataset_id_for(entry: Path) -> str:
    return entry.name


def file_relative_to_dataset(file_path: Path, dataset_path: Path) -> str:
    if dataset_path.is_file():
        return dataset_path.name
    return file_path.relative_to(dataset_path).as_posix()


def inventory(
    root: Path,
    max_text_bytes: int,
    full_hash_limit_bytes: int,
) -> tuple[list[FileRecord], dict[str, list[FileRecord]]]:
    records: list[FileRecord] = []
    by_dataset: dict[str, list[FileRecord]] = defaultdict(list)

    entries = dataset_entries(root)
    total_files_seen = 0
    print(f"[1/6] Inventariando {len(entries)} entradas de primer nivel…")

    for index, entry in enumerate(entries, start=1):
        dataset_id = dataset_id_for(entry)
        print(f"  [{index}/{len(entries)}] {dataset_id}")
        for path in iter_dataset_files(entry):
            total_files_seen += 1
            try:
                stat = path.stat()
                readable = os.access(path, os.R_OK)
                ext = normalized_extension(path)
                should_read_text = (
                    ext in (
                        REFERENCE_EXTENSIONS
                        | DOCUMENT_EXTENSIONS
                        | {".txt", ".csv", ".tsv", ".dat", ".xyz", ".asc"}
                    )
                    and stat.st_size <= max_text_bytes * 5
                )
                text = safe_read_text(path, max_text_bytes) if should_read_text else ""
                numeric_likelihood, _numeric_info = looks_numeric_text(text)
                role, confidence, notes = classify_file(path, text, numeric_likelihood)
                keywords = detect_keywords(text, path.name)

                qfp = quick_fingerprint(path)
                sha256 = (
                    full_sha256(path)
                    if stat.st_size <= full_hash_limit_bytes
                    else f"sampled:{qfp}"
                )

                record = FileRecord(
                    dataset_id=dataset_id,
                    dataset_path=str(entry.resolve()),
                    relative_path=file_relative_to_dataset(path, entry),
                    absolute_path=str(path.resolve()),
                    name=path.name,
                    extension=ext,
                    size_bytes=stat.st_size,
                    modified_utc=utc_timestamp(stat.st_mtime),
                    mime_type=mimetypes.guess_type(path.name)[0] or "",
                    role=role,
                    role_confidence=confidence,
                    readable=readable,
                    is_archive=ext in ARCHIVE_EXTENSIONS,
                    sha256=sha256,
                    quick_fingerprint=qfp,
                    numeric_text_likelihood=numeric_likelihood,
                    detected_keywords=keywords,
                    notes=notes,
                )
            except OSError as exc:
                record = FileRecord(
                    dataset_id=dataset_id,
                    dataset_path=str(entry.resolve()),
                    relative_path=file_relative_to_dataset(path, entry),
                    absolute_path=str(path.resolve()),
                    name=path.name,
                    extension=normalized_extension(path),
                    size_bytes=0,
                    modified_utc="",
                    mime_type="",
                    role="rejected",
                    role_confidence="high",
                    readable=False,
                    is_archive=False,
                    sha256="",
                    quick_fingerprint="",
                    numeric_text_likelihood="no",
                    detected_keywords=[],
                    notes=f"Filesystem error: {exc}",
                )
            records.append(record)
            by_dataset[dataset_id].append(record)

    print(f"  Total de archivos: {total_files_seen}")
    return records, by_dataset


def exact_duplicate_files(records: list[FileRecord]) -> dict[str, list[FileRecord]]:
    groups: dict[str, list[FileRecord]] = defaultdict(list)
    for record in records:
        if record.sha256 and not record.sha256.startswith("sampled:"):
            groups[record.sha256].append(record)
    return {digest: items for digest, items in groups.items() if len(items) > 1}


def dataset_manifest_hash(records: list[FileRecord]) -> str:
    digest = hashlib.sha256()
    normalized = sorted(
        (
            record.relative_path.lower(),
            record.size_bytes,
            record.sha256,
        )
        for record in records
    )
    for rel_path, size, sha256 in normalized:
        digest.update(rel_path.encode("utf-8", errors="ignore"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(sha256.encode("ascii", errors="ignore"))
        digest.update(b"\n")
    return digest.hexdigest()


def exact_duplicate_datasets(
    by_dataset: dict[str, list[FileRecord]]
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for dataset_id, records in by_dataset.items():
        groups[dataset_manifest_hash(records)].append(dataset_id)
    return {digest: ids for digest, ids in groups.items() if len(ids) > 1}


def run_spmkit_probes(
    by_dataset: dict[str, list[FileRecord]],
    command: str,
    timeout: int,
) -> list[ProbeResult]:
    executable = shutil.which(command)
    if not executable:
        print(f"[aviso] No encontré '{command}' en PATH. Se omiten probes.")
        return []

    print("[3/6] Ejecutando probes no destructivos con SPM-Kit…")
    results: list[ProbeResult] = []

    for dataset_id, records in by_dataset.items():
        for record in records:
            if record.extension not in SUPPORTED_SPMKIT_PROBE_EXTENSIONS:
                continue

            cmd = [executable, "info", record.absolute_path]
            started = time.monotonic()
            try:
                completed = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
                elapsed = time.monotonic() - started
                results.append(
                    ProbeResult(
                        dataset_id=dataset_id,
                        relative_path=record.relative_path,
                        command=" ".join(cmd),
                        exit_code=completed.returncode,
                        timed_out=False,
                        runtime_seconds=round(elapsed, 3),
                        success=completed.returncode == 0,
                        stdout=completed.stdout[-12000:],
                        stderr=completed.stderr[-12000:],
                    )
                )
            except subprocess.TimeoutExpired as exc:
                elapsed = time.monotonic() - started
                results.append(
                    ProbeResult(
                        dataset_id=dataset_id,
                        relative_path=record.relative_path,
                        command=" ".join(cmd),
                        exit_code=None,
                        timed_out=True,
                        runtime_seconds=round(elapsed, 3),
                        success=False,
                        stdout=(exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
                        stderr=(exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "",
                    )
                )
            except OSError as exc:
                elapsed = time.monotonic() - started
                results.append(
                    ProbeResult(
                        dataset_id=dataset_id,
                        relative_path=record.relative_path,
                        command=" ".join(cmd),
                        exit_code=None,
                        timed_out=False,
                        runtime_seconds=round(elapsed, 3),
                        success=False,
                        stdout="",
                        stderr=str(exc),
                    )
                )

    print(f"  Probes ejecutados: {len(results)}")
    return results


def infer_dataset(
    dataset_id: str,
    dataset_path: Path,
    records: list[FileRecord],
    probes: list[ProbeResult],
    duplicate_dataset_group: str,
    duplicate_file_membership: set[str],
) -> DatasetRecord:
    roles = Counter(record.role for record in records)
    keywords = Counter(
        keyword for record in records for keyword in record.detected_keywords
    )

    raw_available = roles["raw_instrument"] > 0
    height_matrix = roles["height_matrix"] > 0 or roles["processed_topography"] > 0
    # A textual mention is not a numerical reference.
    # Reference availability requires a file classified as reference data.
    ref_roughness = roles["reference_metrics"] > 0
    ref_psd = roles["reference_psd"] > 0
    ref_acf = roles["reference_acf"] > 0
    units_known = keywords["units"] > 0
    dimensions_known = keywords["dimensions"] > 0
    instrument_known = any(
        keywords[tag] > 0 for tag in ("afm", "spm", "profilometry", "interferometry")
    )
    has_doi = keywords["doi"] > 0
    has_license = keywords["license"] > 0
    repeated = keywords["repeated"] > 0
    multiscale = keywords["multiscale"] > 0
    known_tip_radius = keywords["tip_radius"] > 0

    successful_probes = sum(result.success for result in probes)
    failed_probes = len(probes) - successful_probes
    spmkit_readable = successful_probes > 0

    if (raw_available or height_matrix) and (ref_roughness or ref_psd or ref_acf):
        primary = "topography_benchmark_candidate"
    elif (raw_available or height_matrix) and (multiscale or repeated):
        primary = "multiscale_crosscheck_candidate"
    elif (raw_available or height_matrix) and ref_psd:
        primary = "spectral_crosscheck_candidate"
    elif (raw_available or height_matrix) and ref_roughness:
        primary = "roughness_crosscheck_candidate"
    elif raw_available:
        primary = "reader_fixture"
    elif height_matrix:
        primary = "processed_reference_only"
    elif roles["publication"] or roles["metadata"] or roles["image_preview"]:
        primary = "documentation_only"
    elif roles["rejected"] == len(records) and records:
        primary = "rejected"
    else:
        primary = "incomplete"

    tags: list[str] = []
    for tag in (
        "afm", "spm", "profilometry", "interferometry", "roughness", "psd",
        "acf", "doi", "license", "tip_radius", "repeated", "multiscale",
    ):
        if keywords[tag] > 0:
            normalized = {
                "roughness": "has_reference_roughness",
                "psd": "has_reference_psd",
                "acf": "has_reference_acf",
                "doi": "has_doi",
                "license": "has_license",
                "tip_radius": "known_tip_radius",
                "repeated": "repeated_measurements",
            }.get(tag, tag)
            tags.append(normalized)

    if raw_available:
        tags.append("raw_available")
    if height_matrix:
        tags.append("height_matrix_available")
    if duplicate_dataset_group:
        tags.append("duplicate")
    if roles["archive"] and len(records) == roles["archive"]:
        tags.append("archive_only")
    if not units_known:
        tags.append("uncertain_units")
    if raw_available or height_matrix:
        tags.append("uncertain_orientation")

    score = 0
    if raw_available or height_matrix:
        score += 30
    if raw_available:
        score += 15
    if ref_roughness:
        score += 15
    if ref_psd or ref_acf:
        score += 15
    if units_known and dimensions_known:
        score += 10
    elif units_known or dimensions_known:
        score += 5
    if has_doi:
        score += 5
    if has_license:
        score += 5
    if repeated or multiscale:
        score += 5
    if instrument_known or known_tip_radius:
        score += 5

    if not units_known:
        score -= 20
    if not dimensions_known:
        score -= 10
    if roles["image_preview"] and not (raw_available or height_matrix):
        score -= 20
    if not (raw_available or height_matrix):
        score -= 25
    if roles["rejected"]:
        score -= 10
    if duplicate_dataset_group:
        score -= 10
    if records and all(not record.readable for record in records):
        score -= 30

    score = max(0, min(100, score))

    if score >= 80:
        priority = "priority_a"
    elif score >= 60:
        priority = "priority_b"
    elif score >= 40:
        priority = "priority_c"
    else:
        priority = "manual_or_reject"

    manual_review = (
        priority in {"priority_a", "priority_b"}
        or primary in {"incomplete", "rejected"}
        or (raw_available or height_matrix) and not units_known
        or failed_probes > 0
    )

    notes: list[str] = []
    if failed_probes:
        notes.append(f"{failed_probes} SPM-Kit probe(s) failed")
    if not units_known and (raw_available or height_matrix):
        notes.append("Units not detected automatically")
    if duplicate_dataset_group:
        notes.append(f"Exact duplicate dataset group {duplicate_dataset_group}")

    return DatasetRecord(
        dataset_id=dataset_id,
        local_path=str(dataset_path.resolve()),
        total_size_bytes=sum(record.size_bytes for record in records),
        file_count=len(records),
        primary_utility=primary,
        secondary_tags=sorted(set(tags)),
        triage_score=score,
        priority=priority,
        raw_available=raw_available,
        height_matrix_available=height_matrix,
        reference_roughness=ref_roughness,
        reference_psd=ref_psd,
        reference_acf=ref_acf,
        units_known=units_known,
        dimensions_known=dimensions_known,
        instrument_known=instrument_known,
        has_doi=has_doi,
        has_license=has_license,
        spmkit_readable=spmkit_readable,
        spmkit_probe_successes=successful_probes,
        spmkit_probe_failures=failed_probes,
        duplicate_group=duplicate_dataset_group,
        manual_review_required=manual_review,
        notes="; ".join(notes),
    )


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            normalized = {
                key: (
                    json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (list, dict))
                    else value
                )
                for key, value in row.items()
            }
            writer.writerow(normalized)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def make_reports(
    output: Path,
    datasets: list[DatasetRecord],
    records: list[FileRecord],
    duplicate_files: dict[str, list[FileRecord]],
    duplicate_datasets: dict[str, list[str]],
) -> None:
    utility_counts = Counter(dataset.primary_utility for dataset in datasets)
    priority_counts = Counter(dataset.priority for dataset in datasets)
    role_counts = Counter(record.role for record in records)
    total_size = sum(record.size_bytes for record in records)

    report_lines = [
        "# SPM-Kit / Fathom Validation Dataset Classification",
        "",
        f"Generated: `{datetime.now(timezone.utc).isoformat()}`",
        "",
        "## Summary",
        "",
        f"- Datasets: **{len(datasets)}**",
        f"- Files: **{len(records)}**",
        f"- Total size: **{human_size(total_size)}**",
        f"- Exact duplicate file groups: **{len(duplicate_files)}**",
        f"- Exact duplicate dataset groups: **{len(duplicate_datasets)}**",
        f"- SPM-Kit-readable datasets: **{sum(d.spmkit_readable for d in datasets)}**",
        "",
        "## Priority distribution",
        "",
    ]
    for priority, count in sorted(priority_counts.items()):
        report_lines.append(f"- `{priority}`: {count}")

    report_lines += ["", "## Utility distribution", ""]
    for utility, count in sorted(utility_counts.items()):
        report_lines.append(f"- `{utility}`: {count}")

    report_lines += ["", "## File-role distribution", ""]
    for role, count in sorted(role_counts.items()):
        report_lines.append(f"- `{role}`: {count}")

    report_lines += [
        "",
        "## Highest-priority candidates",
        "",
        "| Dataset | Score | Priority | Utility | Files | Size | SPM-Kit readable |",
        "|---|---:|---|---|---:|---:|---|",
    ]
    for dataset in sorted(datasets, key=lambda d: (-d.triage_score, d.dataset_id))[:20]:
        report_lines.append(
            f"| `{dataset.dataset_id}` | {dataset.triage_score} | `{dataset.priority}` | "
            f"`{dataset.primary_utility}` | {dataset.file_count} | "
            f"{human_size(dataset.total_size_bytes)} | "
            f"{'yes' if dataset.spmkit_readable else 'no'} |"
        )

    report_lines += [
        "",
        "## Interpretation",
        "",
        "- **Reader/parser testing** checks whether SPM-Kit can load the file correctly.",
        "- **Algorithm cross-checking** compares derived values under matched preprocessing.",
        "- **Scientific validation** requires documented units, calibration, "
        "processing conventions, provenance, and human review.",
        "",
        "A high triage score is not a scientific validation claim.",
    ]
    (output / "CLASSIFICATION_REPORT.md").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )

    queue_lines = [
        "# Human Review Queue",
        "",
        "Review the smallest high-value subset rather than every file.",
        "",
    ]

    sections = [
        ("Priority A", [d for d in datasets if d.priority == "priority_a"]),
        ("Priority B", [d for d in datasets if d.priority == "priority_b"]),
        (
            "Reference PSD / ACF",
            [d for d in datasets if d.reference_psd or d.reference_acf],
        ),
        (
            "Reader fixtures",
            [d for d in datasets if d.primary_utility == "reader_fixture"],
        ),
        (
            "Ambiguous units",
            [
                d
                for d in datasets
                if (d.raw_available or d.height_matrix_available) and not d.units_known
            ],
        ),
        (
            "SPM-Kit probe failures",
            [d for d in datasets if d.spmkit_probe_failures > 0],
        ),
        (
            "Duplicates",
            [d for d in datasets if bool(d.duplicate_group)],
        ),
        (
            "Rejected or incomplete",
            [d for d in datasets if d.primary_utility in {"rejected", "incomplete"}],
        ),
    ]

    for title, items in sections:
        queue_lines += [f"## {title}", ""]
        if not items:
            queue_lines += ["_None._", ""]
            continue
        for dataset in sorted(items, key=lambda d: (-d.triage_score, d.dataset_id))[:20]:
            reason = dataset.notes or dataset.primary_utility
            queue_lines.append(
                f"- `{dataset.dataset_id}` — score {dataset.triage_score}, "
                f"`{dataset.primary_utility}`. Path: `{dataset.local_path}`. {reason}"
            )
        queue_lines.append("")

    (output / "HUMAN_REVIEW_QUEUE.md").write_text(
        "\n".join(queue_lines) + "\n", encoding="utf-8"
    )

    dup_lines = [
        "# Duplicate Analysis",
        "",
        "No source files were deleted or modified.",
        "",
        "## Exact duplicate files",
        "",
    ]
    if not duplicate_files:
        dup_lines.append("_No exact duplicate file groups found._")
    else:
        for index, (digest, items) in enumerate(sorted(duplicate_files.items()), start=1):
            dup_lines += [
                f"### File group F{index:03d}",
                "",
                f"- SHA-256: `{digest}`",
                f"- Copies: {len(items)}",
                f"- Size per copy: {human_size(items[0].size_bytes)}",
                "",
            ]
            for item in items:
                dup_lines.append(f"  - `{item.absolute_path}`")
            dup_lines.append("")

    dup_lines += ["## Exact duplicate datasets", ""]
    if not duplicate_datasets:
        dup_lines.append("_No exact duplicate dataset groups found._")
    else:
        for index, (digest, ids) in enumerate(sorted(duplicate_datasets.items()), start=1):
            dup_lines += [
                f"### Dataset group D{index:03d}",
                "",
                f"- Manifest hash: `{digest}`",
                "",
            ]
            for dataset_id in ids:
                dup_lines.append(f"  - `{dataset_id}`")
            dup_lines.append("")

    (output / "DUPLICATES.md").write_text(
        "\n".join(dup_lines) + "\n", encoding="utf-8"
    )


def make_symlink_views(output: Path, datasets: list[DatasetRecord]) -> None:
    print("[5/6] Creando vistas organizadas con symlinks…")
    roots = {
        "by-priority": lambda d: d.priority,
        "by-utility": lambda d: d.primary_utility,
    }
    for root_name, classifier in roots.items():
        base = output / root_name
        for dataset in datasets:
            category = classifier(dataset)
            destination_dir = base / category
            destination_dir.mkdir(parents=True, exist_ok=True)
            link = destination_dir / dataset.dataset_id
            if link.exists() or link.is_symlink():
                continue
            try:
                source_path = Path(dataset.local_path)
                link.symlink_to(source_path, target_is_directory=source_path.is_dir())
            except OSError:
                # Windows or restricted filesystems may block symlinks.
                index = destination_dir / "INDEX.txt"
                with index.open("a", encoding="utf-8") as handle:
                    handle.write(f"{dataset.dataset_id}\t{dataset.local_path}\n")


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()

    if not root.exists() or not root.is_dir():
        print(f"Error: dataset root does not exist or is not a directory: {root}", file=sys.stderr)
        return 2

    output = (
        args.output.expanduser().resolve()
        if args.output
        else (root.parent / "validation" / "triage").resolve()
    )
    output.mkdir(parents=True, exist_ok=True)

    try:
        if output == root or output.is_relative_to(root):
            print(
                "Error: output must be outside the immutable dataset root.",
                file=sys.stderr,
            )
            return 2
    except AttributeError:
        # Python 3.8 fallback, though Python 3.11+ is expected.
        if str(output).startswith(str(root) + os.sep):
            print("Error: output must be outside the immutable dataset root.", file=sys.stderr)
            return 2

    print("SPM-Kit validation dataset classifier")
    print(f"Source (read-only): {root}")
    print(f"Output:             {output}")
    print()

    full_hash_limit_bytes = int(args.full_hash_limit_gb * 1024**3)

    records, by_dataset = inventory(
        root=root,
        max_text_bytes=args.max_text_inspection_bytes,
        full_hash_limit_bytes=full_hash_limit_bytes,
    )

    print("[2/6] Detectando duplicados exactos…")
    duplicate_files = exact_duplicate_files(records)
    duplicate_datasets = exact_duplicate_datasets(by_dataset)

    dataset_group_lookup: dict[str, str] = {}
    for index, (_digest, ids) in enumerate(sorted(duplicate_datasets.items()), start=1):
        group_name = f"D{index:03d}"
        for dataset_id in ids:
            dataset_group_lookup[dataset_id] = group_name

    duplicate_file_membership = {
        item.absolute_path
        for items in duplicate_files.values()
        for item in items
    }

    probes: list[ProbeResult] = []
    if args.probe_spmkit:
        probes = run_spmkit_probes(
            by_dataset=by_dataset,
            command=args.spmkit_command,
            timeout=args.probe_timeout,
        )
    else:
        print("[3/6] Probes SPM-Kit omitidos. Usa --probe-spmkit para activarlos.")

    probes_by_dataset: dict[str, list[ProbeResult]] = defaultdict(list)
    for probe in probes:
        probes_by_dataset[probe.dataset_id].append(probe)

    print("[4/6] Clasificando datasets…")
    entries_by_id = {dataset_id_for(entry): entry for entry in dataset_entries(root)}
    datasets = [
        infer_dataset(
            dataset_id=dataset_id,
            dataset_path=entries_by_id[dataset_id],
            records=dataset_records,
            probes=probes_by_dataset.get(dataset_id, []),
            duplicate_dataset_group=dataset_group_lookup.get(dataset_id, ""),
            duplicate_file_membership=duplicate_file_membership,
        )
        for dataset_id, dataset_records in sorted(by_dataset.items())
    ]

    file_rows = [asdict(record) for record in records]
    dataset_rows = [asdict(dataset) for dataset in datasets]
    probe_rows = [asdict(probe) for probe in probes]

    write_csv(
        output / "file_inventory.csv",
        file_rows,
        list(FileRecord.__dataclass_fields__.keys()),
    )
    write_jsonl(output / "file_inventory.jsonl", file_rows)

    write_csv(
        output / "VALIDATION_MATRIX.csv",
        dataset_rows,
        list(DatasetRecord.__dataclass_fields__.keys()),
    )
    write_jsonl(output / "VALIDATION_MATRIX.jsonl", dataset_rows)

    write_csv(
        output / "spmkit_probe_results.csv",
        probe_rows,
        list(ProbeResult.__dataclass_fields__.keys()),
    )
    write_jsonl(output / "spmkit_probe_results.jsonl", probe_rows)

    duplicate_file_rows: list[dict[str, Any]] = []
    for index, (digest, items) in enumerate(sorted(duplicate_files.items()), start=1):
        group = f"F{index:03d}"
        for item in items:
            duplicate_file_rows.append(
                {
                    "group": group,
                    "sha256": digest,
                    "size_bytes": item.size_bytes,
                    "dataset_id": item.dataset_id,
                    "relative_path": item.relative_path,
                    "absolute_path": item.absolute_path,
                }
            )
    write_csv(
        output / "duplicate_files.csv",
        duplicate_file_rows,
        ["group", "sha256", "size_bytes", "dataset_id", "relative_path", "absolute_path"],
    )

    duplicate_dataset_rows: list[dict[str, Any]] = []
    for index, (digest, ids) in enumerate(sorted(duplicate_datasets.items()), start=1):
        group = f"D{index:03d}"
        for dataset_id in ids:
            duplicate_dataset_rows.append(
                {
                    "group": group,
                    "manifest_hash": digest,
                    "dataset_id": dataset_id,
                    "local_path": str(entries_by_id[dataset_id].resolve()),
                }
            )
    write_csv(
        output / "duplicate_datasets.csv",
        duplicate_dataset_rows,
        ["group", "manifest_hash", "dataset_id", "local_path"],
    )

    make_reports(
        output=output,
        datasets=datasets,
        records=records,
        duplicate_files=duplicate_files,
        duplicate_datasets=duplicate_datasets,
    )

    if args.symlinks:
        make_symlink_views(output, datasets)
    else:
        print("[5/6] Vistas por symlink omitidas. Usa --symlinks para crearlas.")

    print("[6/6] Verificando archivos generados…")
    for jsonl_path in (
        output / "file_inventory.jsonl",
        output / "VALIDATION_MATRIX.jsonl",
        output / "spmkit_probe_results.jsonl",
    ):
        with jsonl_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if line.strip():
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(
                            f"Invalid JSONL in {jsonl_path}:{line_number}: {exc}"
                        ) from exc

    print()
    print("Listo.")
    print(f"  Datasets: {len(datasets)}")
    print(f"  Archivos: {len(records)}")
    print(f"  Duplicados de archivo: {len(duplicate_files)} grupos")
    print(f"  Duplicados de dataset: {len(duplicate_datasets)} grupos")
    print(f"  Priority A: {sum(d.priority == 'priority_a' for d in datasets)}")
    print(f"  SPM-Kit readable: {sum(d.spmkit_readable for d in datasets)}")
    print()
    print(f"Abre primero: {output / 'CLASSIFICATION_REPORT.md'}")
    print(f"Después:      {output / 'HUMAN_REVIEW_QUEUE.md'}")
    print(f"Matriz:       {output / 'VALIDATION_MATRIX.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
