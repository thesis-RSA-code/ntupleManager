#!/usr/bin/env python3
"""Extract train/val/test split from a hierarchical HDF5 file using NPZ indices.

GhostHunter stores event indices in an NPZ with keys ``train``, ``val``, ``test``.
Each index refers to ``event_<idx>`` in the source HDF5. The output file renumbers
events sequentially as ``event_0``, ``event_1``, ... so downstream loaders see a
contiguous dataset (as expected by BaseHDF5Dataset).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import h5py
import numpy as np

SPLIT_KEYS = ("train", "val", "test", "train_val")


def load_split_indices(npz_path: Path, split: str) -> np.ndarray:
    data = np.load(npz_path)
    if split == "train_val":
        for key in ("train", "val"):
            if key not in data.files:
                raise KeyError(
                    f"Split key '{key}' not found in {npz_path} "
                    f"(required for train_val); available: {list(data.files)}"
                )
        return np.concatenate(
            [np.asarray(data["train"], dtype=np.int64), np.asarray(data["val"], dtype=np.int64)]
        )
    if split not in data.files:
        raise KeyError(
            f"Split key '{split}' not found in {npz_path}; available: {list(data.files)}"
        )
    return np.asarray(data[split], dtype=np.int64)


def source_event_count(src: h5py.File) -> int | None:
    """Return event count from root attrs when available (avoids scanning 1M+ groups)."""
    for attr in ("n_events", "num_events", "n_event"):
        if attr in src.attrs:
            return int(src.attrs[attr])
    return None


def copy_root_attrs(
    src: h5py.File,
    dst: h5py.File,
    *,
    split: str,
    indices: np.ndarray,
    npz_path: Path,
    input_path: Path,
) -> None:
    for key, value in src.attrs.items():
        dst.attrs[key] = value
    dst.attrs["split_name"] = split
    dst.attrs["extracted_split"] = split  # legacy alias
    dst.attrs["indices_file"] = str(npz_path)
    dst.attrs["split_indices_file"] = str(npz_path)  # legacy alias
    dst.attrs["source_file"] = str(input_path)
    dst.attrs["source_hdf5_file"] = str(input_path)  # legacy alias
    dst.attrs["n_events"] = len(indices)
    dst.attrs["extracted_by"] = "extract_hdf5_split.py"


def copy_event_group(src: h5py.File, dst: h5py.File, src_name: str, dst_name: str) -> None:
    src.copy(src_name, dst, dst_name)


def extract_split(
    input_path: Path,
    indices_path: Path,
    split: str,
    output_path: Path,
    *,
    progress_every: int = 10_000,
) -> dict:
    indices = load_split_indices(indices_path, split)
    n_indices = len(indices)
    if n_indices == 0:
        raise ValueError(f"Split '{split}' is empty in {indices_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    t0 = time.perf_counter()
    copied = 0
    missing = []

    with h5py.File(input_path, "r") as src, h5py.File(output_path, "w") as dst:
        n_source = source_event_count(src)
        max_idx = int(indices.max())
        if n_source is not None and max_idx >= n_source:
            raise ValueError(
                f"Largest index in split ({max_idx}) >= source event count ({n_source}); "
                f"indices file may belong to a different HDF5."
            )
        if n_source is None:
            print(
                f"  (no n_events root attr; skipping pre-check, max index={max_idx})",
                flush=True,
            )

        copy_root_attrs(
            src,
            dst,
            split=split,
            indices=indices,
            npz_path=indices_path,
            input_path=input_path,
        )

        for out_idx, src_idx in enumerate(indices):
            src_name = f"event_{src_idx}"
            dst_name = f"event_{out_idx}"
            if src_name not in src:
                missing.append(int(src_idx))
                continue
            copy_event_group(src, dst, src_name, dst_name)
            copied += 1

            if progress_every > 0 and copied % progress_every == 0:
                elapsed = time.perf_counter() - t0
                rate = copied / elapsed if elapsed > 0 else 0.0
                print(
                    f"  copied {copied}/{n_indices} events "
                    f"({100.0 * copied / n_indices:.1f}%) "
                    f"[{rate:.1f} events/s]",
                    flush=True,
                )

    elapsed = time.perf_counter() - t0
    if missing:
        raise RuntimeError(
            f"Missing {len(missing)} source events (first few: {missing[:10]})"
        )

    with h5py.File(output_path, "r") as out:
        n_out = int(out.attrs.get("n_events", copied))

    if n_out != n_indices:
        raise RuntimeError(
            f"Output event count mismatch: expected {n_indices}, found {n_out}"
        )

    return {
        "n_indices": n_indices,
        "n_copied": copied,
        "elapsed_s": elapsed,
        "output_path": output_path,
        "output_size_bytes": output_path.stat().st_size,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract a train/val/test/train_val split from hierarchical HDF5 using NPZ indices."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Source hierarchical HDF5 file",
    )
    parser.add_argument(
        "--indices",
        required=True,
        type=Path,
        help="NPZ file with train/val/test index arrays",
    )
    parser.add_argument(
        "--split",
        choices=SPLIT_KEYS,
        default="test",
        help=(
            "Which split to extract: train, val, test, or train_val "
            "(train then val concatenated; default: test)"
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output HDF5 file path",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10_000,
        help="Print progress every N events (default: 10000; 0 to disable)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.input.exists():
        print(f"ERROR: input file not found: {args.input}", file=sys.stderr)
        return 1
    if not args.indices.exists():
        print(f"ERROR: indices file not found: {args.indices}", file=sys.stderr)
        return 1

    indices = load_split_indices(args.indices, args.split)
    print(f"Input:   {args.input}")
    print(f"Indices: {args.indices}")
    print(f"Split:   {args.split} ({len(indices)} events)")
    print(f"Output:  {args.output}")

    stats = extract_split(
        args.input,
        args.indices,
        args.split,
        args.output,
        progress_every=args.progress_every,
    )

    size_gb = stats["output_size_bytes"] / (1024**3)
    print(
        f"Done: copied {stats['n_copied']} events in {stats['elapsed_s']:.1f}s "
        f"({size_gb:.3f} GiB) -> {stats['output_path']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
