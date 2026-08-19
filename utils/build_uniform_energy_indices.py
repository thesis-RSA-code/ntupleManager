#!/usr/bin/env python3
"""Build energy-uniform index lists from a WatChMaL flat Super-K ``.hy`` file.

Unlike ``utils/build_sk_smoke_indices.py`` (which takes the FIRST N keep_event rows
of a given label, and therefore inherits whatever local energy bias the leading ROOT
jobs happen to have), this script does **stratified sampling**: the requested energy
window is split into equal-width bins and the same number of events is drawn at
random from each bin.  The resulting spectrum is flat *by construction*, not merely
flat in expectation.

Selection applied before sampling (so that what is requested is what gets written):
    keep_event == True
    labels == --label                      (0=mu-, 1=e-, 2=pi+ for this production)
    --e-min <= energies[i,0] <= --e-max     (TOTAL energy, rest mass included;
                                             both edges INCLUSIVE, omit for native range)
    n_hits_raw >= --min-n-hits-raw         (off by default)

``keep_event`` alone does *not* distort the spectrum on this production: the generator
sampled uniformly in total energy from the Cherenkov threshold over a 2000 MeV span, and
the 1,273,400 surviving events per label are still flat to ~1%.  The bias seen in the
existing smoke sets comes from ``build_sk_smoke_indices.py`` taking the first N
*contiguous* keep rows, i.e. a handful of ROOT jobs.

``n_hits_raw`` is ``diff(event_hits_index)``, i.e. hits *before* the ``--min-hit-charge``
filter that ``hy_flat_to_hier_hdf5.py`` applies.  Measured on this production the
0.11 p.e. cut keeps >= 97.5% of hits per event (median 99.5%), so a raw threshold of
210 would safely guarantee >= 200 hits after the charge cut.  If you do want the
converter's ``--min-n-hits``, set it here instead: that cut is strongly energy-correlated
(it eats ~24% of the lowest energy bin and nothing else) and, left to the converter, it
is applied *after* the sample was drawn and silently re-biases it.

Output NPZ carries the source row indices **sorted ascending** (h5py fancy indexing
requires increasing order, and the converter feeds them straight to
``src["energies"][chunk_idx, 0]``).  The array is stored under key ``indices`` and
aliased as ``event_idx`` / ``keep_event_idx`` so it works with any of the three
defaults floating around in this repo.

Usage:
    python build_uniform_energy_indices.py \\
        --hy /sps/.../multi_combine.hy --label 1 --n-events 1000 \\
        --e-min 200 --e-max 2000 --n-bins 20 --min-n-hits-raw 210 \\
        --output-npz /sps/.../uniform_energy/e-_uniform_1k_indices.npz
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

LABEL_NAMES = {0: "mu-", 1: "e-", 2: "pi+"}
TAG = "[uniform-idx]"


def _load_metadata(hy_file: Path | None, meta_cache: Path | None) -> dict:
    """Return labels / keep_event / energies / n_hits_raw for every source row."""
    if meta_cache is not None and meta_cache.exists():
        print(f"{TAG} loading cached metadata from {meta_cache}")
        d = np.load(meta_cache)
        meta = {
            "labels": d["labels"],
            "keep_event": d["keep_event"],
            "energies": d["energies"],
            "n_hits_raw": d["n_hits_raw"],
        }
        print(f"{TAG}   cache holds {len(meta['labels']):,} rows")
        return meta

    if hy_file is None:
        raise ValueError("--hy is required when --meta-cache is absent or missing")

    import h5py

    print(f"{TAG} reading event-level metadata from {hy_file}")
    with h5py.File(hy_file, "r") as src:
        labels = src["labels"][:].astype(np.int32)
        keep = src["keep_event"][:]
        energies = src["energies"][:, 0].astype(np.float32)
        ehi = src["event_hits_index"][:].astype(np.int64)
        total_hits = int(src["hit_charge"].shape[0])
    n_hits_raw = np.diff(np.append(ehi, total_hits))
    print(f"{TAG}   {len(labels):,} rows, {total_hits:,} hits total")

    meta = {
        "labels": labels,
        "keep_event": keep,
        "energies": energies,
        "n_hits_raw": n_hits_raw,
    }
    if meta_cache is not None:
        meta_cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(meta_cache, total_hits=np.int64(total_hits), **meta)
        print(f"{TAG}   cached metadata -> {meta_cache}")
    return meta


def _print_hist(energies: np.ndarray, e_min: float, e_max: float, n_bins: int,
                tag: str) -> None:
    h, _ = np.histogram(energies, bins=n_bins, range=(e_min, e_max))
    print(f"{TAG}   {tag} (n={len(energies)}): " + " ".join(f"{v}" for v in h))


def build(
    hy_file: Path | None,
    meta_cache: Path | None,
    label: int,
    n_events: int,
    e_min: float | None,
    e_max: float | None,
    n_bins: int,
    min_n_hits_raw: int,
    seed: int,
    output_npz: Path | None,
) -> tuple[np.ndarray, dict]:
    name = LABEL_NAMES.get(label, f"label_{label}")

    meta = _load_metadata(hy_file, meta_cache)
    labels = meta["labels"]
    keep = meta["keep_event"]
    energies = meta["energies"]
    n_hits_raw = meta["n_hits_raw"]

    n_total = len(labels)
    m_keep = keep
    m_label = m_keep & (labels == label)
    m_pre = m_label & (n_hits_raw >= min_n_hits_raw)

    # Native window = full energy span of the post-keep_event pool for this label.
    pool_e = energies[m_pre]
    if len(pool_e) == 0:
        raise RuntimeError(f"no keep_event rows with label={label} ({name})")
    if e_min is None:
        e_min = float(pool_e.min())
        print(f"{TAG} --e-min omitted -> native lower edge {e_min:.3f} MeV")
    if e_max is None:
        e_max = float(pool_e.max())
        print(f"{TAG} --e-max omitted -> native upper edge {e_max:.3f} MeV")

    print(f"{TAG} target: {n_events} events of label={label} ({name}), "
          f"uniform over total energy [{e_min:.3f}, {e_max:.3f}] MeV in {n_bins} bins")

    m_energy = m_pre & (energies >= e_min) & (energies <= e_max)
    m_hits = m_energy

    print(f"{TAG} selection cascade:")
    print(f"{TAG}   all rows                       : {n_total:,}")
    print(f"{TAG}   keep_event == True             : {m_keep.sum():,}")
    print(f"{TAG}   & label == {label} ({name:4s})          : {m_label.sum():,}")
    print(f"{TAG}   & n_hits_raw >= {min_n_hits_raw:<5d}          : {m_pre.sum():,}")
    print(f"{TAG}   & {e_min:.1f} <= E <= {e_max:.1f}    : {m_energy.sum():,}")

    candidates = np.flatnonzero(m_hits)
    if len(candidates) < n_events:
        raise RuntimeError(
            f"only {len(candidates):,} candidates for label={label} ({name}) "
            f"in [{e_min}, {e_max}); need {n_events}"
        )
    cand_e = energies[candidates]
    _print_hist(cand_e, e_min, e_max, n_bins, "candidate pool")

    # --- stratified draw: equal count per energy bin -------------------------
    edges = np.linspace(e_min, e_max, n_bins + 1)
    bin_of = np.clip(np.digitize(cand_e, edges) - 1, 0, n_bins - 1)

    rng = np.random.default_rng(seed)
    per_bin = np.full(n_bins, n_events // n_bins, dtype=np.int64)
    remainder = n_events - int(per_bin.sum())
    if remainder:
        # spread the leftover over distinct random bins so no bin gets +2
        per_bin[rng.choice(n_bins, size=remainder, replace=False)] += 1
        print(f"{TAG} {n_events} is not a multiple of {n_bins} bins: "
              f"{remainder} bin(s) get one extra event")

    picked: list[np.ndarray] = []
    short_bins: list[tuple[int, int, int]] = []
    for k in range(n_bins):
        pool = candidates[bin_of == k]
        want = int(per_bin[k])
        if len(pool) < want:
            short_bins.append((k, len(pool), want))
            picked.append(pool)
        else:
            picked.append(rng.choice(pool, size=want, replace=False))

    if short_bins:
        deficit = sum(want - have for _, have, want in short_bins)
        print(f"{TAG} !! WARNING: {len(short_bins)} bin(s) under-supplied "
              f"(total deficit {deficit}) — the output will NOT be perfectly flat:")
        for k, have, want in short_bins:
            print(f"{TAG}      bin {k:2d} [{edges[k]:.1f}, {edges[k+1]:.1f}): "
                  f"have {have}, want {want}")
        already = np.concatenate(picked)
        spare = np.setdiff1d(candidates, already, assume_unique=False)
        if len(spare) < deficit:
            raise RuntimeError(
                f"cannot top up {deficit} events: only {len(spare)} spare candidates"
            )
        print(f"{TAG}    topping up {deficit} event(s) from the remaining pool")
        picked.append(rng.choice(spare, size=deficit, replace=False))

    selected = np.sort(np.concatenate(picked)).astype(np.int64)
    assert len(np.unique(selected)) == len(selected), "duplicate indices selected"
    sel_e = energies[selected]
    sel_h = n_hits_raw[selected]

    print(f"{TAG} selected {len(selected):,} events")
    _print_hist(sel_e, e_min, e_max, n_bins, "SELECTED spectrum")
    print(f"{TAG}   energy    : min={sel_e.min():.2f} max={sel_e.max():.2f} "
          f"mean={sel_e.mean():.1f} MeV")
    print(f"{TAG}   n_hits_raw: min={sel_h.min()} med={int(np.median(sel_h))} "
          f"max={sel_h.max()}")
    print(f"{TAG}   row range : {selected[0]:,} .. {selected[-1]:,}")

    info = {
        "label": int(label),
        "label_name": name,
        "n_selected": int(len(selected)),
        "e_min": float(e_min),
        "e_max": float(e_max),
        "n_bins": int(n_bins),
        "min_n_hits_raw": int(min_n_hits_raw),
        "seed": int(seed),
        "n_candidates": int(len(candidates)),
        "short_bins": short_bins,
    }

    if output_npz is not None:
        output_npz.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            output_npz,
            indices=selected,
            event_idx=selected,       # alias: sk_hy_to_h5_slurm.sh default key
            keep_event_idx=selected,  # alias: hy_flat_to_hier_hdf5.py default key
            energies=sel_e,
            n_hits_raw=sel_h,
            selected_label=np.int32(label),
            selected_label_name=name,
            hy_file=str(hy_file) if hy_file else "",
            e_min=np.float32(e_min),
            e_max=np.float32(e_max),
            n_bins=np.int64(n_bins),
            min_n_hits_raw=np.int64(min_n_hits_raw),
            seed=np.int64(seed),
            n_candidates=np.int64(len(candidates)),
        )
        print(f"{TAG} wrote {len(selected):,} sorted indices -> {output_npz} "
              f"(key 'indices', aliases 'event_idx' / 'keep_event_idx')")

    return selected, info


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--hy", type=Path, default=None, help="Input flat .hy HDF5 path.")
    p.add_argument("--meta-cache", type=Path, default=None,
                   help="NPZ cache of event-level metadata; read if present, else written.")
    p.add_argument("--label", type=int, required=True,
                   help="Particle label to select (this production: 0=mu-, 1=e-, 2=pi+).")
    p.add_argument("--n-events", type=int, default=1000, help="Events to select.")
    p.add_argument("--e-min", type=float, default=None,
                   help="Lower edge (inclusive) of the uniform window, MeV TOTAL energy. "
                        "Omit for the label's native minimum.")
    p.add_argument("--e-max", type=float, default=None,
                   help="Upper edge (inclusive) of the uniform window, MeV TOTAL energy. "
                        "Omit for the label's native maximum.")
    p.add_argument("--n-bins", type=int, default=20,
                   help="Stratification bins over the window (default: 20).")
    p.add_argument("--min-n-hits-raw", type=int, default=0,
                   help="Minimum pre-charge-cut hits (default: 0 = off; use 210 to "
                        "guarantee >= 200 hits after the 0.11 p.e. charge filter).")
    p.add_argument("--seed", type=int, default=0, help="RNG seed (default: 0).")
    p.add_argument("--output-npz", type=Path, default=None, help="Output NPZ path.")
    return p


if __name__ == "__main__":
    args = _build_argparser().parse_args()
    build(
        hy_file=args.hy,
        meta_cache=args.meta_cache,
        label=args.label,
        n_events=args.n_events,
        e_min=args.e_min,
        e_max=args.e_max,
        n_bins=args.n_bins,
        min_n_hits_raw=args.min_n_hits_raw,
        seed=args.seed,
        output_npz=args.output_npz,
    )
