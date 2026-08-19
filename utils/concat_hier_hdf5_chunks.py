#!/usr/bin/env python3
"""Concatenate hierarchical GhostHunter HDF5 chunk files into one dataset.

Each chunk file is expected to contain ``event_0`` … ``event_{N-1}`` (local numbering).
The output file renumbers events globally as ``event_0``, ``event_1``, …

Chunk paths are sorted by optional ``_chunk_XXXXX`` suffix in the filename, then
lexicographically. Uses ``h5py.Group.copy`` (no full-RAM load).

Optional ``--stage-dir``: copy each chunk to local disk before reading (frees staging
file after each chunk when ``--stage-cleanup`` is set).
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path

import h5py
import numpy as np

CHUNK_SUFFIX_RE = re.compile(r"_chunk_(\d+)$")
_SKIP_COPY_ATTRS = frozenset({
    "chunk_files",
    "n_chunk_files",
    "chunk_first",
    "chunk_last",
    "concatenated_by",
    "output_file",
    "staged_from",
})
_ATTR_CHUNK_FILES_MAX_BYTES = 48_000
_ATTR_CHUNK_FILES_MAX_COUNT = 64


def _chunk_sort_key(path: Path) -> tuple[int, str]:
    m = CHUNK_SUFFIX_RE.search(path.stem)
    if m:
        return (int(m.group(1)), path.name)
    return (10**9, path.name)


def resolve_chunk_paths(pattern: str | None, paths: list[Path]) -> list[Path]:
    found: list[Path] = list(paths)
    if pattern:
        pat = Path(pattern)
        if pat.parent.exists():
            found.extend(sorted(pat.parent.glob(pat.name)))
        else:
            found.extend(sorted(Path().glob(pattern)))
    if not found:
        raise FileNotFoundError("No chunk HDF5 files matched the inputs.")
    return sorted({p.resolve() for p in found}, key=_chunk_sort_key)


def count_events_in_chunk(src: h5py.File) -> int:
    if "n_events" in src.attrs:
        return int(src.attrs["n_events"])
    return sum(1 for k in src.keys() if k.startswith("event_"))


def _store_chunk_provenance(
    dst: h5py.File,
    chunk_paths: list[Path],
    *,
    output_path: Path,
    stage_dir: Path | None,
) -> None:
    path_strs = [str(p) for p in chunk_paths]
    total_bytes = sum(len(s.encode("utf-8")) for s in path_strs)
    dst.attrs["concatenated_by"] = "concat_hier_hdf5_chunks.py"
    dst.attrs["n_chunk_files"] = len(chunk_paths)
    dst.attrs["chunk_first"] = path_strs[0]
    dst.attrs["chunk_last"] = path_strs[-1]
    dst.attrs["output_file"] = str(output_path)
    if stage_dir is not None:
        dst.attrs["staged_from"] = str(stage_dir)

    if len(path_strs) <= _ATTR_CHUNK_FILES_MAX_COUNT and total_bytes < _ATTR_CHUNK_FILES_MAX_BYTES:
        dst.attrs["chunk_files"] = np.array(path_strs, dtype="S")
    else:
        vlen_str = h5py.special_dtype(vlen=str)
        dst.create_dataset("chunk_files", data=np.array(path_strs, dtype=object), dtype=vlen_str)


def copy_root_attrs(
    first: h5py.File,
    dst: h5py.File,
    *,
    chunk_paths: list[Path],
    output_path: Path,
    stage_dir: Path | None = None,
) -> None:
    for key, value in first.attrs.items():
        if key in _SKIP_COPY_ATTRS:
            continue
        dst.attrs[key] = value
    _store_chunk_provenance(dst, chunk_paths, output_path=output_path, stage_dir=stage_dir)


def _stage_chunk(chunk_path: Path, stage_dir: Path) -> Path:
    stage_dir.mkdir(parents=True, exist_ok=True)
    staged = stage_dir / chunk_path.name
    if staged.exists() and staged.stat().st_size == chunk_path.stat().st_size:
        return staged
    print(f"  staging {chunk_path.name} -> {staged}", flush=True)
    shutil.copy2(chunk_path, staged)
    return staged


def concat_chunks(
    chunk_paths: list[Path],
    output_path: Path,
    *,
    progress_every: int = 10_000,
    stage_dir: Path | None = None,
    stage_cleanup: bool = True,
) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    t0 = time.perf_counter()
    stage_t0 = time.perf_counter()
    stage_bytes = 0
    written = 0
    skipped_empty = 0

    with h5py.File(output_path, "w") as dst:
        with h5py.File(chunk_paths[0], "r") as first:
            copy_root_attrs(
                first, dst, chunk_paths=chunk_paths, output_path=output_path, stage_dir=stage_dir
            )

        for chunk_no, chunk_path in enumerate(chunk_paths, start=1):
            read_path = chunk_path
            staged_path: Path | None = None
            if stage_dir is not None:
                staged_path = _stage_chunk(chunk_path, stage_dir)
                read_path = staged_path
                stage_bytes += read_path.stat().st_size

            with h5py.File(read_path, "r") as src:
                n_local = count_events_in_chunk(src)
                if n_local == 0:
                    skipped_empty += 1
                    print(f"  chunk {chunk_no}/{len(chunk_paths)}: empty, skip {chunk_path.name}")
                    if staged_path is not None and stage_cleanup:
                        staged_path.unlink(missing_ok=True)
                    continue

                local_indices = sorted(
                    int(k.split("_", 1)[1])
                    for k in src.keys()
                    if k.startswith("event_")
                )
                if local_indices and (
                    local_indices[0] != 0
                    or local_indices[-1] != len(local_indices) - 1
                    or len(local_indices) != n_local
                ):
                    print(
                        f"  warning: {chunk_path.name} event groups may be non-contiguous; "
                        f"copying {len(local_indices)} groups in sorted order",
                        flush=True,
                    )

                for local_idx in local_indices:
                    src_name = f"event_{local_idx}"
                    dst_name = f"event_{written}"
                    src.copy(src_name, dst, dst_name)
                    written += 1

                    if progress_every > 0 and written % progress_every == 0:
                        elapsed = time.perf_counter() - t0
                        rate = written / elapsed if elapsed > 0 else 0.0
                        print(
                            f"  concatenated {written} events "
                            f"({rate:.1f} events/s, chunk {chunk_no}/{len(chunk_paths)})",
                            flush=True,
                        )

            if staged_path is not None and stage_cleanup:
                staged_path.unlink(missing_ok=True)

    with h5py.File(output_path, "a") as out:
        out.attrs["n_events"] = written

    elapsed = time.perf_counter() - t0
    stage_elapsed = time.perf_counter() - stage_t0
    return {
        "n_chunks": len(chunk_paths),
        "n_chunks_empty": skipped_empty,
        "n_events": written,
        "elapsed_s": elapsed,
        "stage_bytes": stage_bytes,
        "stage_elapsed_s": stage_elapsed if stage_dir is not None else 0.0,
        "output_path": output_path,
        "output_size_bytes": output_path.stat().st_size,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Concatenate hierarchical HDF5 chunk files (event_0..N per chunk)."
    )
    parser.add_argument(
        "--glob",
        dest="glob_pattern",
        default=None,
        help="Glob for chunk files (e.g. '/data/out_chunk_*.h5')",
    )
    parser.add_argument(
        "chunks",
        nargs="*",
        type=Path,
        help="Explicit chunk HDF5 paths (sorted with --glob results if both given)",
    )
    parser.add_argument("--output", required=True, type=Path, help="Merged output HDF5 path")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10_000,
        help="Print progress every N events (default: 10000; 0 to disable)",
    )
    parser.add_argument(
        "--stage-dir",
        type=Path,
        default=None,
        help="Copy each chunk here before reading (e.g. /tmp/sk_hy_chunks_<jobid>)",
    )
    parser.add_argument(
        "--no-stage-cleanup",
        action="store_true",
        help="Keep staged chunk files after each chunk is processed",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        chunk_paths = resolve_chunk_paths(args.glob_pattern, args.chunks)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Chunks:  {len(chunk_paths)} files")
    print(f"  first: {chunk_paths[0]}")
    print(f"  last:  {chunk_paths[-1]}")
    print(f"Output:  {args.output}")
    if args.stage_dir is not None:
        print(f"Stage:   {args.stage_dir} (cleanup={not args.no_stage_cleanup})")

    stats = concat_chunks(
        chunk_paths,
        args.output,
        progress_every=args.progress_every,
        stage_dir=args.stage_dir,
        stage_cleanup=not args.no_stage_cleanup,
    )
    size_gb = stats["output_size_bytes"] / (1024**3)
    stage_gb = stats["stage_bytes"] / (1024**3)
    print(
        f"Done: {stats['n_events']} events from {stats['n_chunks']} chunks "
        f"({stats['n_chunks_empty']} empty) in {stats['elapsed_s']:.1f}s "
        f"({size_gb:.3f} GiB) -> {stats['output_path']}"
    )
    if args.stage_dir is not None:
        print(f"Staged {stage_gb:.3f} GiB total to {args.stage_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
