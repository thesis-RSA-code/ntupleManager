#!/usr/bin/env python3
"""Empirical consistency check for an energy-uniform subset produced by
``build_uniform_energy_indices.py`` + ``hy_flat_to_hier_hdf5.py``.

Cross-checks the written hierarchical HDF5 against the index NPZ that produced it:

  1. event count matches the NPZ
  2. per-event ``energy`` matches ``energies[indices]`` from the source .hy, IN ORDER
     (catches the classic "arrays written in a different order than the metadata" bug)
  3. ``event_type`` is the requested label everywhere
  4. the energy spectrum is flat over the requested window
  5. ``n_digi_hits`` <= the source ``n_hits_raw`` and equals len(pmt_charge/time/tube_ids)
  6. charge respects the --min-hit-charge / --max-hit-charge window

Exit status is non-zero if any check fails.

Usage:
    python verify_uniform_subset.py --h5 OUT.h5 --indices-npz IDX.npz [--n-bins 20]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import h5py
import numpy as np

TAG = "[verify]"
LABEL_NAMES = {0: "mu-", 1: "e-", 2: "pi+"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--h5", required=True, type=Path, help="Hierarchical HDF5 to check.")
    p.add_argument("--indices-npz", required=True, type=Path,
                   help="Index NPZ used to build it.")
    p.add_argument("--n-bins", type=int, default=20, help="Bins for the flatness check.")
    p.add_argument("--min-hit-charge", type=float, default=0.11)
    p.add_argument("--max-hit-charge", type=float, default=51.0)
    args = p.parse_args()

    idx = np.load(args.indices_npz, allow_pickle=True)
    src_indices = idx["indices"]
    src_energy = idx["energies"]
    src_nraw = idx["n_hits_raw"]
    label = int(idx["selected_label"])
    name = LABEL_NAMES.get(label, str(label))
    e_min, e_max = float(idx["e_min"]), float(idx["e_max"])
    print(f"{TAG} index NPZ : {args.indices_npz}")
    print(f"{TAG}   {len(src_indices):,} source rows, label={label} ({name}), "
          f"window [{e_min:.3f}, {e_max:.3f}] MeV")

    failures: list[str] = []

    with h5py.File(args.h5, "r") as f:
        attrs = dict(f.attrs)
        groups = [k for k in f.keys() if k.startswith("event_")]
        n_ev = len(groups)
        print(f"{TAG} HDF5      : {args.h5}")
        print(f"{TAG}   {n_ev:,} event groups, root attr n_events={attrs.get('n_events')}")
        print(f"{TAG}   source_file={attrs.get('source_file')}")

        # 1. count
        if n_ev != len(src_indices):
            failures.append(
                f"event count {n_ev} != {len(src_indices)} indices requested "
                f"(converter dropped events -- the spectrum is NO LONGER flat)"
            )

        order = np.argsort([int(g.split("_")[1]) for g in groups])
        groups = [groups[i] for i in order]

        energy = np.empty(n_ev, np.float64)
        etype = np.empty(n_ev, np.int64)
        ndigi = np.empty(n_ev, np.int64)
        arr_len = np.empty((n_ev, 3), np.int64)
        qmin, qmax = np.inf, -np.inf
        tmin, tmax = np.inf, -np.inf
        tid_min, tid_max = np.inf, -np.inf
        for i, g in enumerate(groups):
            ev = f[g]
            energy[i] = ev["energy"][()]
            etype[i] = ev["event_type"][()]
            ndigi[i] = ev["n_digi_hits"][()]
            q = ev["pmt_charge"][:]
            t = ev["pmt_time"][:]
            tid = ev["tube_ids"][:]
            arr_len[i] = (len(q), len(t), len(tid))
            qmin, qmax = min(qmin, q.min()), max(qmax, q.max())
            tmin, tmax = min(tmin, t.min()), max(tmax, t.max())
            tid_min, tid_max = min(tid_min, tid.min()), max(tid_max, tid.max())

    # 2. per-event energy vs the source, in order
    if n_ev == len(src_indices):
        d = np.abs(energy - src_energy.astype(np.float64))
        print(f"{TAG} energy vs source .hy: max |diff| = {d.max():.3e} MeV")
        if d.max() > 1e-3:
            n_bad = int((d > 1e-3).sum())
            failures.append(
                f"{n_bad} events have energy != energies[indices] "
                f"(max diff {d.max():.3e} MeV) -> ORDERING MISMATCH"
            )
        else:
            print(f"{TAG}   OK: events are written in index order, metadata aligned")

    # 3. label
    bad_type = int((etype != label).sum())
    print(f"{TAG} event_type: unique={np.unique(etype).tolist()} (expected {label} = {name})")
    if bad_type:
        failures.append(f"{bad_type} events have event_type != {label}")

    # 4. flatness
    h, _ = np.histogram(energy, bins=args.n_bins, range=(e_min, e_max))
    print(f"{TAG} spectrum ({args.n_bins} bins over [{e_min:.1f}, {e_max:.1f}]):")
    print(f"{TAG}   " + " ".join(str(v) for v in h))
    print(f"{TAG}   min={h.min()} max={h.max()} sum={h.sum()} "
          f"(energy range in file: {energy.min():.2f} .. {energy.max():.2f} MeV)")
    if h.sum() != n_ev:
        failures.append(f"{n_ev - h.sum()} events fall outside the requested window")
    if h.max() - h.min() > 1:
        failures.append(f"spectrum not flat: bins span {h.min()}..{h.max()}")

    # 5. hit-count consistency
    ragged = int((arr_len[:, 0] != ndigi).sum() + (arr_len[:, 1] != ndigi).sum()
                 + (arr_len[:, 2] != ndigi).sum())
    print(f"{TAG} n_digi_hits: min={ndigi.min()} med={int(np.median(ndigi))} "
          f"max={ndigi.max()} total={ndigi.sum():,}")
    if ragged:
        failures.append(f"{ragged} pmt_charge/pmt_time/tube_ids lengths != n_digi_hits")
    if n_ev == len(src_indices):
        over = int((ndigi > src_nraw).sum())
        surv = ndigi.sum() / src_nraw.sum()
        print(f"{TAG}   vs source n_hits_raw: kept {100 * surv:.2f}% of hits "
              f"(charge filter at {args.min_hit_charge} p.e.)")
        if over:
            failures.append(f"{over} events have more hits than the source raw count")

    # 6. hit-level ranges
    print(f"{TAG} pmt_charge: [{qmin:.4f}, {qmax:.4f}] p.e.   "
          f"pmt_time: [{tmin:.2f}, {tmax:.2f}] ns   tube_ids: [{int(tid_min)}, {int(tid_max)}]")
    if qmin < args.min_hit_charge - 1e-6:
        failures.append(f"charge {qmin} below --min-hit-charge {args.min_hit_charge}")
    if qmax > args.max_hit_charge + 1e-6:
        failures.append(f"charge {qmax} above --max-hit-charge {args.max_hit_charge}")

    print()
    if failures:
        print(f"{TAG} !! {len(failures)} CHECK(S) FAILED:")
        for msg in failures:
            print(f"{TAG}    - {msg}")
        return 1
    print(f"{TAG} ALL CHECKS PASSED for {args.h5.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
