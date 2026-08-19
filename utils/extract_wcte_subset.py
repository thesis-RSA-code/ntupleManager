#!/usr/bin/env python3
"""Extract a random subset of the WCTE e- production into a standalone hierarchical HDF5.

    extract_wcte_subset.py --n 10000 --out <file.h5> [--charge-min X] [--seed S]

Writes the subset plus, next to it, a .npz holding the source indices actually used, so
the sample can be traced back to the production (and re-drawn identically).

With --charge-min, every PER-HIT array is filtered by the same mask and `n_digi_hits` is
recomputed. Filtering the charge alone would silently desynchronise it from pmt_time,
tube_ids and the hit coordinates, which is the classic way to corrupt one of these files.

Note on "raw": the production already stores a minimum charge of exactly 0.0100 p.e., so a
file written without --charge-min is raw *as stored*, not raw out of the digitiser.
"""

import argparse
import time

import h5py
import numpy as np

# every array that is one-entry-per-hit and must be filtered together
HIT_FIELDS = ("pmt_charge", "pmt_time", "tube_ids", "mPMT_tube_ids", "hitx", "hity", "hitz")


def probe_n_events(h):
    """The concatenated production carries no n_events attr; find the count by bisection."""
    if "n_events" in h.attrs:
        return int(h.attrs["n_events"])
    lo, hi = 0, 4_000_000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if f"event_{mid - 1}" in h:
            lo = mid
        else:
            hi = mid - 1
    return lo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/sps/t2k/eleblevec/Datasets/prod_datasets/wcte_prod/"
                                     "h5/WCTE_uni_iso_FC_e-_0-1000MeV_TRAIN_VAL_TEST.h5")
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260807)
    ap.add_argument("--charge-min", type=float, default=None)
    args = ap.parse_args()

    t0 = time.time()
    src = h5py.File(args.src, "r")
    n_src = probe_n_events(src)
    print(f"[extract] source      : {args.src}")
    print(f"[extract] n_events    : {n_src}")

    rng = np.random.default_rng(args.seed)
    idx = np.sort(rng.choice(n_src, args.n, replace=False))
    print(f"[extract] drawing     : {args.n} events, seed {args.seed}")
    print(f"[extract] charge cut  : {'none (raw as stored)' if args.charge_min is None else f'>= {args.charge_min} p.e.'}")

    out = h5py.File(args.out, "w")
    fields = sorted(src["event_0"].keys())
    print(f"[extract] fields      : {', '.join(fields)}")

    n_hits_before = n_hits_after = 0
    for k, i in enumerate(idx):
        g_in = src[f"event_{i}"]
        g_out = out.create_group(f"event_{k}")
        if args.charge_min is None:
            mask = None
        else:
            mask = g_in["pmt_charge"][:] >= args.charge_min
        for name in fields:
            arr = g_in[name][()]
            if mask is not None and name in HIT_FIELDS:
                arr = arr[mask]
            if name == "n_digi_hits" and mask is not None:
                arr = np.array(int(mask.sum()), dtype=np.int32)
            g_out.create_dataset(name, data=arr)
        n_hits_before += int(g_in["n_digi_hits"][()])
        n_hits_after += int(g_out["n_digi_hits"][()])
        if (k + 1) % 2000 == 0:
            print(f"[extract]   {k + 1}/{args.n} events, {time.time() - t0:.0f} s", flush=True)

    out.attrs["n_events"] = args.n
    out.attrs["source_file"] = args.src
    out.attrs["source_n_events"] = n_src
    out.attrs["draw_seed"] = args.seed
    out.attrs["charge_min"] = "none" if args.charge_min is None else args.charge_min
    out.attrs["indices_file"] = args.out.replace(".h5", "_indices.npz")
    out.close()
    src.close()

    np.savez(args.out.replace(".h5", "_indices.npz"),
             indices=idx, seed=args.seed, source_n_events=n_src,
             source_file=args.src,
             charge_min=(np.nan if args.charge_min is None else args.charge_min))

    print(f"[extract] hits        : {n_hits_before} -> {n_hits_after} "
          f"({100 * (1 - n_hits_after / max(n_hits_before, 1)):.3f}% removed)")
    print(f"[extract] wrote       : {args.out}")
    print(f"[extract] indices     : {args.out.replace('.h5', '_indices.npz')}")
    print(f"[extract] elapsed     : {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
