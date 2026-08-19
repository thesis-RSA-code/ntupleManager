#!/usr/bin/env python3
"""Extract row indices where keep_event[i] is True from a WatChMaL flat .hy file."""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import numpy as np


def extract(input_file: Path, output_file: Path) -> dict:
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    if "keep_event" not in h5py.File(input_file, "r"):
        raise RuntimeError(f"'keep_event' dataset missing in {input_file}")

    with h5py.File(input_file, "r") as src:
        keep = src["keep_event"][:]
    n_total = int(keep.shape[0])
    keep_event_idx = np.flatnonzero(keep).astype(np.int64)
    n_keep = int(keep_event_idx.shape[0])

    output_file.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        output_file,
        keep_event_idx=keep_event_idx,
        n_total=np.int64(n_total),
        n_keep=np.int64(n_keep),
        source_file=str(input_file),
    )
    print(
        f"Wrote {n_keep:,} keep_event indices (of {n_total:,} total) "
        f"to {output_file}"
    )
    return {
        "n_total": n_total,
        "n_keep": n_keep,
        "output_file": str(output_file),
    }


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path, help="Input flat .hy HDF5 path.")
    p.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output .npz path (key: keep_event_idx).",
    )
    return p


if __name__ == "__main__":
    args = _build_argparser().parse_args()
    extract(input_file=args.input, output_file=args.output)
