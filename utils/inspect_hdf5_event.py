#!/usr/bin/env python3
"""Print root attrs and datasets for event_<N> in an HDF5 file."""
import argparse
import sys

import h5py
import numpy as np


def print_attrs(obj, indent=0):
    prefix = "  " * indent
    if not obj.attrs:
        print(f"{prefix}(no attrs)")
        return
    for k, v in obj.attrs.items():
        print(f"{prefix}{k}: {v}")


def describe_dataset(name, ds, max_array: int):
    print(f"  {name}: dtype={ds.dtype}, shape={ds.shape}")
    if ds.shape == ():
        print(f"    value: {ds[()]}")
        return
    if ds.ndim == 1:
        arr = ds[()]
        print(f"    min={np.min(arr)}, max={np.max(arr)}, mean={np.mean(arr):.6g}")
        n = min(max_array, arr.size)
        print(f"    first {n}: {arr[:n]}")
        return
    # multi-D: stats on flat view if numeric
    if np.issubdtype(ds.dtype, np.number):
        flat = ds[()].ravel()
        print(f"    min={np.min(flat)}, max={np.max(flat)}, mean={np.mean(flat):.6g}")


def main():
    p = argparse.ArgumentParser(description="Inspect event_<N> in an HDF5 file.")
    p.add_argument("--file", required=True, help="Path to HDF5 file")
    p.add_argument("--event", type=int, default=0, help="Event index (default: 0)")
    p.add_argument("--max-array", type=int, default=10, help="Max 1D elements to print")
    args = p.parse_args()

    group_name = f"event_{args.event}"
    with h5py.File(args.file, "r") as f:
        print(f"File: {args.file}")
        print("Root attributes:")
        print_attrs(f, indent=1)
        if group_name not in f:
            print(f"ERROR: group '{group_name}' not found.", file=sys.stderr)
            sys.exit(1)
        g = f[group_name]
        print(f"\nGroup: {group_name}")
        for name in sorted(g.keys()):
            describe_dataset(name, g[name], args.max_array)


if __name__ == "__main__":
    main()
