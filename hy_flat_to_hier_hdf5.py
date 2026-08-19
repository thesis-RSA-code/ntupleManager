#!/usr/bin/env python3
"""
WatChMaL flat Super-K ``.hy`` HDF5 -> hierarchical GhostHunter HDF5.

Input layout (flat root datasets, no per-event groups):
    event_hits_index  — cumulative hit start per event; event *i* hits are
                        ``hit_*[idx[i] : idx[i+1])`` (last event uses total hit length)
    hit_charge, hit_time, hit_pmt — global jagged hit arrays
    energies (N,1), positions (N,1,3), directions (N,1,3), labels (N,)
    keep_event, event_ids, veto, … — optional metadata

Output layout (same schema as HK/WCTE producers):
    /event_<i>/n_digi_hits, energy, event_type, vertex_*, particle_dir_*,
    pmt_charge, pmt_time, tube_ids (int32)

Field mapping (WatChMaL flat -> GhostHunter hierarchical)
-----------------------------------------------------------------
| .hy source              | HDF5 target              | dtype   |
|-------------------------|--------------------------|---------|
| slice length            | n_digi_hits              | int32   |
| energies[i, 0]          | energy                   | float32 |
| labels[i]               | event_type               | int32   |
| positions[i, 0, *]      | vertex_x/y/z             | float32 |
| directions[i, 0, *]     | particle_dir_x/y/z       | float32 |
| hit_charge[s:e]         | pmt_charge               | float32 |
| hit_time[s:e]           | pmt_time                 | float32 |
| hit_pmt[s:e]            | tube_ids                 | int32   |

``labels`` is a WatChMaL class index (stored as-is in ``event_type``, **not** PDG) and
its meaning is **production-dependent** — do not assume it.  For the SK-IV particle-gun
production ``Datasets/sk_iv/pgun_ccan/`` (``multi_combine.hy``) it is:

    0 = mu-,  1 = e-,  2 = pi+

verified 2026-08-03 from the per-label energy minima, which land exactly on the water
Cherenkov thresholds: mu- 159.92 MeV (= sqrt(120^2 + 105.66^2)), e- 0.50 MeV,
pi+ 211.58 MeV (= sqrt(159^2 + 139.57^2)).  ``energies`` is therefore **total** energy,
rest mass included.  Note this also means ``event_ids`` is *not* the particle type — it
is the 0-based event id inside the source ROOT job (0..998).

To identify the mapping in a new production, histogram ``energies`` per label value: the
minimum of each is the Cherenkov threshold of that particle (e 0, mu 159.9, pi 211.6 MeV
total energy in water).  ``utils/build_sk_smoke_indices.py`` and
``utils/build_uniform_energy_indices.py`` carry the same table in ``LABEL_NAMES``.

GhostHunter HK/WCTE ntuples typically use PDG codes (11, 13, 22, …).
Remap downstream if your training config expects PDG.

PMT xyz are not in ``.hy``; GhostHunter resolves positions from geometry NPZ
via ``tube_ids`` when ``detector="SK"`` and the NPZ exists.

Optional scalars (dwall, towall, trigger_time) are omitted when absent.

Per-hit charge handling (``pmt_charge``, ``pmt_time``, ``tube_ids`` stay aligned):
    ``--min-hit-charge`` — remove hits with charge strictly below the threshold.
    ``--max-hit-charge`` — keep hits above the cap but set charge to the cap (p.e.).

Felix-style event cuts (``--min-n-hits``, ``--max-energy``) are applied after
per-hit charge filtering.  The ``fcM50`` fiducial cut is **not** present
in WatChMaL ``.hy`` files and is therefore not applied here.

Usage:
    python hy_flat_to_hier_hdf5.py --input PATH --output PATH \\
        [--start 0] [--stop N] [--step 1] \\
        [--keep-event-only] [--max-events N] \\
        [--indices-npz PATH] [--indices-key keep_event_idx] \\
        [--start-event I] [--num-events N] \\
        [--chunk-index I --events-per-chunk N]  # SLURM array slice -> output_chunk_XXXXX.h5 \\
        [--min-hit-charge 0.11] [--max-hit-charge 51.0] [--min-n-hits 200] [--max-energy 2000] \\
        [--chunk-size 500]  # RAM read batch, not SLURM output size \\
        [--max-hit-gap 4096]  # coalesce hit reads separated by fewer than N hits

Scattered index lists (e.g. an energy-stratified sample drawn from the whole file) are
handled efficiently: hits are read as *contiguous runs* of the requested events, so the
RAM cost of a chunk is proportional to the hits actually needed, not to the file span
the chunk happens to cover.  See ``_read_hit_block``.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Iterator

import h5py
import numpy as np

try:
    from utils.hdf5_writer import HDF5GraphWriter
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from utils.hdf5_writer import HDF5GraphWriter


REQUIRED_DATASETS = (
    "event_hits_index",
    "hit_charge",
    "hit_time",
    "hit_pmt",
    "energies",
    "positions",
    "directions",
    "labels",
)

WATCHMAL_LABEL_DOC = (
    "WatChMaL class index, not PDG; production-dependent. "
    "sk_iv/pgun_ccan: 0=mu-, 1=e-, 2=pi+ (verified from Cherenkov thresholds "
    "in the per-label energy minima; energies are TOTAL energy)"
)


def _check_schema(src: h5py.File) -> int:
    """Validate required datasets; return number of events."""
    missing = [k for k in REQUIRED_DATASETS if k not in src]
    if missing:
        raise RuntimeError(
            f"Input .hy file missing required datasets: {missing}. "
            f"Found: {sorted(src.keys())}"
        )
    n_events = int(src["energies"].shape[0])
    if src["event_hits_index"].shape[0] != n_events:
        raise RuntimeError(
            "event_hits_index length "
            f"({src['event_hits_index'].shape[0]}) != energies rows ({n_events})"
        )
    return n_events


def _source_indices(
    n_events: int,
    start: int,
    stop: int | None,
    step: int,
) -> np.ndarray:
    if stop is None:
        stop = n_events
    if start < 0 or start >= n_events:
        raise ValueError(f"--start {start} out of range [0, {n_events})")
    if stop < 0 or stop > n_events:
        raise ValueError(f"--stop {stop} out of range [0, {n_events}]")
    if step < 1:
        raise ValueError(f"--step must be >= 1, got {step}")
    return np.arange(start, stop, step, dtype=np.int64)


def _load_indices_npz(path: Path, key: str) -> np.ndarray:
    data = np.load(path)
    if key not in data.files:
        raise KeyError(
            f"Key '{key}' not found in {path}. Available: {list(data.files)}"
        )
    idx = np.asarray(data[key], dtype=np.int64).ravel()
    return idx


def _slice_index_list(
    indices: np.ndarray,
    *,
    start_event: int | None,
    num_events: int | None,
    chunk_index: int | None,
    events_per_chunk: int | None,
) -> tuple[np.ndarray, dict]:
    """Slice the ordered source-index list for SLURM array / partial conversion."""
    meta: dict = {}
    n_total = len(indices)
    meta["index_list_length"] = n_total

    if start_event is not None:
        if start_event < 0 or start_event > n_total:
            raise ValueError(
                f"--start-event {start_event} out of range [0, {n_total}]"
            )
        indices = indices[start_event:]
        meta["start_event"] = start_event
    else:
        meta["start_event"] = 0

    if num_events is not None:
        if num_events < 1:
            raise ValueError(f"--num-events must be >= 1, got {num_events}")
        indices = indices[:num_events]
        meta["num_events"] = num_events

    if chunk_index is not None:
        if events_per_chunk is None:
            raise ValueError("--events-per-chunk is required with --chunk-index")
        if events_per_chunk < 1:
            raise ValueError(
                f"--events-per-chunk must be >= 1, got {events_per_chunk}"
            )
        if chunk_index < 0:
            raise ValueError(f"--chunk-index must be >= 0, got {chunk_index}")
        lo = chunk_index * events_per_chunk
        hi = lo + events_per_chunk
        meta["chunk_index"] = chunk_index
        meta["events_per_chunk"] = events_per_chunk
        meta["chunk_index_range"] = (lo, hi)
        indices = indices[lo:hi]

    return indices, meta


def _chunk_output_path(output_file: Path, chunk_index: int | None) -> Path:
    if chunk_index is None:
        return output_file
    stem = output_file.stem
    suffix = output_file.suffix or ".h5"
    if "_chunk_" in stem:
        return output_file
    return output_file.parent / f"{stem}_chunk_{chunk_index:05d}{suffix}"


def _iter_event_chunks(indices: np.ndarray, chunk_size: int) -> Iterator[np.ndarray]:
    for off in range(0, len(indices), chunk_size):
        yield indices[off : off + chunk_size]


def _hit_spans(
    hit_index_ds: h5py.Dataset,
    chunk_src_idx: np.ndarray,
    total_hits: int,
    n_events: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return per-event ``[start, end)`` hit slices for the events in a chunk.

    ``chunk_src_idx`` must be sorted ascending and unique (h5py fancy indexing
    requires it; ``convert`` enforces it).  Two vectorised reads replace the
    per-event scalar lookups the old code did.
    """
    starts = np.asarray(hit_index_ds[chunk_src_idx], dtype=np.int64)
    ends = np.empty(len(chunk_src_idx), dtype=np.int64)
    nxt = chunk_src_idx + 1
    is_last = nxt >= n_events
    ends[is_last] = total_hits
    if not is_last.all():
        ends[~is_last] = np.asarray(hit_index_ds[nxt[~is_last]], dtype=np.int64)
    return starts, ends


def _read_hit_block(
    src: h5py.File,
    starts: np.ndarray,
    ends: np.ndarray,
    max_hit_gap: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    """Read the hits of a chunk into one buffer, one read per *contiguous run*.

    The previous implementation read a single ``[min(starts), max(ends))`` block.
    That is fine for a contiguous index list, but for a scattered one (an
    energy-stratified sample, a shuffled split, …) the span covers most of the file:
    500 events drawn uniformly from 1.3 M rows of this production span ~3.5e9 hits,
    i.e. ~14 GB per array — an OOM, for ~1 M hits of actual payload.

    Here, events whose hit ranges are adjacent (or separated by fewer than
    ``max_hit_gap`` hits, so that seeking costs more than over-reading) are merged
    into one run and read in a single call.  A contiguous index list still collapses
    to exactly one read per chunk, so the old fast path is preserved; a fully
    scattered list degrades to one read per event.  Either way RAM is bounded by the
    hits actually requested.

    Returns ``(charge, time, pmt, event_offsets, n_runs)`` where ``event_offsets[j]``
    is where event *j*'s hits begin inside the returned buffers.
    """
    n = len(starts)
    if n == 0:
        empty = np.empty(0, dtype=np.int64)
        return (
            np.empty(0, dtype=src["hit_charge"].dtype),
            np.empty(0, dtype=src["hit_time"].dtype),
            np.empty(0, dtype=src["hit_pmt"].dtype),
            empty,
            0,
        )

    # Runs of events close enough to be worth reading together.  starts/ends are both
    # ascending and non-overlapping (flat jagged layout), so a single pass suffices.
    new_run = np.empty(n, dtype=bool)
    new_run[0] = True
    new_run[1:] = starts[1:] > ends[:-1] + max_hit_gap
    run_of = np.cumsum(new_run) - 1
    first = np.flatnonzero(new_run)
    last = np.append(first[1:] - 1, n - 1)
    run_lo = starts[first]
    run_hi = ends[last]

    run_len = run_hi - run_lo
    run_off = np.concatenate(([0], np.cumsum(run_len)))
    total = int(run_off[-1])

    charge = np.empty(total, dtype=src["hit_charge"].dtype)
    times = np.empty(total, dtype=src["hit_time"].dtype)
    pmts = np.empty(total, dtype=src["hit_pmt"].dtype)
    for r in range(len(run_lo)):
        lo, hi = int(run_lo[r]), int(run_hi[r])
        a, b = int(run_off[r]), int(run_off[r + 1])
        charge[a:b] = src["hit_charge"][lo:hi]
        times[a:b] = src["hit_time"][lo:hi]
        pmts[a:b] = src["hit_pmt"][lo:hi]

    event_offsets = run_off[run_of] + (starts - run_lo[run_of])
    return charge, times, pmts, event_offsets, len(run_lo)


def _filter_hits(
    charges: np.ndarray,
    times: np.ndarray,
    pmts: np.ndarray,
    min_hit_charge: float,
    max_hit_charge: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    if min_hit_charge > 0.0:
        mask = charges >= min_hit_charge
        charges = charges[mask]
        times = times[mask]
        pmts = pmts[mask]
    if max_hit_charge is not None:
        charges = np.clip(charges, None, max_hit_charge)
    return charges, times, pmts, int(charges.shape[0])


def _parse_max_hit_charge(value: str) -> float | None:
    if value.lower() in ("none", "off", "disable"):
        return None
    return float(value)


def convert(
    input_file: Path,
    output_file: Path,
    start: int = 0,
    stop: int | None = None,
    step: int = 1,
    keep_event_only: bool = False,
    max_events: int | None = None,
    chunk_size: int = 500,
    max_hit_gap: int = 4096,
    compression: str = "gzip",
    indices_npz: Path | None = None,
    indices_key: str = "keep_event_idx",
    min_hit_charge: float = 0.11,
    max_hit_charge: float | None = 51.0,
    min_n_hits: int | None = None,
    max_energy: float | None = None,
    start_event: int | None = None,
    num_events: int | None = None,
    chunk_index: int | None = None,
    events_per_chunk: int | None = None,
) -> dict:
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    output_file = _chunk_output_path(output_file, chunk_index)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    written = 0
    skipped_empty = 0
    skipped_keep = 0
    skipped_cuts = 0
    indices_processed = 0
    hits_read = 0
    runs_read = 0

    with h5py.File(input_file, "r") as src:
        n_events = _check_schema(src)
        if indices_npz is not None:
            src_indices = _load_indices_npz(indices_npz, indices_key)
            print(
                f"[hy] loaded {len(src_indices):,} source indices from "
                f"{indices_npz} (key={indices_key})"
            )
        else:
            src_indices = _source_indices(n_events, start, stop, step)

        # h5py fancy indexing requires strictly increasing selections, so every index
        # list that works at all is already sorted; normalising here turns what used to
        # be an opaque h5py error into a warning, and gives each SLURM task a
        # contiguous region of the file to read.
        n_before = len(src_indices)
        if n_before and not np.all(np.diff(src_indices) > 0):
            src_indices = np.unique(src_indices)
            n_dup = n_before - len(src_indices)
            print(
                f"[hy] warning: index list was not strictly increasing; sorted it"
                + (f" and dropped {n_dup:,} duplicate(s)" if n_dup else "")
            )

        src_indices, slice_meta = _slice_index_list(
            src_indices,
            start_event=start_event,
            num_events=num_events,
            chunk_index=chunk_index,
            events_per_chunk=events_per_chunk,
        )
        if len(src_indices) == 0:
            print(
                "[hy] warning: index slice is empty; writing metadata-only HDF5 "
                f"(chunk_index={chunk_index})"
            )

        total_hits = int(src["hit_charge"].shape[0])

        hit_index_ds = src["event_hits_index"]
        has_keep = "keep_event" in src and keep_event_only

        with HDF5GraphWriter(output_file, compression=compression) as writer:
            meta = {
                "source_file": str(input_file),
                "format": "watchmal_flat",
                "geometry": "SK",
                "converter": "hy_flat_to_hier_hdf5.py",
                "watchmal_labels": WATCHMAL_LABEL_DOC,
            }
            if indices_npz is not None:
                meta["indices_npz"] = str(indices_npz)
                meta["indices_key"] = indices_key
            if min_hit_charge > 0.0:
                meta["min_hit_charge"] = min_hit_charge
            if max_hit_charge is not None:
                meta["max_hit_charge"] = max_hit_charge
            meta["max_hit_gap"] = max_hit_gap
            if min_n_hits is not None:
                meta["min_n_hits"] = min_n_hits
            if max_energy is not None:
                meta["max_energy"] = max_energy
            meta.update(slice_meta)
            if chunk_index is not None:
                meta["output_chunk_index"] = chunk_index
            meta["n_events"] = 0
            for k, v in src.attrs.items():
                meta[f"source_{k}"] = v
            writer.add_metadata(**meta)

            n_chunks = (len(src_indices) + chunk_size - 1) // chunk_size
            done = False
            for chunk_no, chunk_idx in enumerate(
                _iter_event_chunks(src_indices, chunk_size), start=1
            ):
                if done or (max_events is not None and written >= max_events):
                    break

                starts_blk, ends_blk = _hit_spans(
                    hit_index_ds, chunk_idx, total_hits, n_events
                )
                (
                    hit_charge_blk,
                    hit_time_blk,
                    hit_pmt_blk,
                    hit_off_blk,
                    n_runs,
                ) = _read_hit_block(src, starts_blk, ends_blk, max_hit_gap)

                energies_blk = src["energies"][chunk_idx, 0].astype(np.float32)
                labels_blk = src["labels"][chunk_idx].astype(np.int32)
                pos_blk = np.squeeze(src["positions"][chunk_idx], axis=1).astype(
                    np.float32
                )
                dir_blk = np.squeeze(src["directions"][chunk_idx], axis=1).astype(
                    np.float32
                )

                if has_keep:
                    keep_blk = src["keep_event"][chunk_idx]
                else:
                    keep_blk = None

                for local_j, src_i in enumerate(chunk_idx):
                    if max_events is not None and written >= max_events:
                        done = True
                        break

                    if keep_blk is not None and not bool(keep_blk[local_j]):
                        skipped_keep += 1
                        continue

                    energy = float(energies_blk[local_j])
                    if max_energy is not None and energy > max_energy:
                        skipped_cuts += 1
                        continue

                    n_hits_raw = int(ends_blk[local_j] - starts_blk[local_j])
                    if n_hits_raw == 0:
                        skipped_empty += 1
                        continue

                    off = int(hit_off_blk[local_j])
                    charges, times, pmts, n_hits = _filter_hits(
                        hit_charge_blk[off : off + n_hits_raw],
                        hit_time_blk[off : off + n_hits_raw],
                        hit_pmt_blk[off : off + n_hits_raw],
                        min_hit_charge,
                        max_hit_charge,
                    )
                    if n_hits == 0:
                        skipped_empty += 1
                        continue
                    if min_n_hits is not None and n_hits < min_n_hits:
                        skipped_cuts += 1
                        continue

                    event_data = {
                        "n_digi_hits": np.int32(n_hits),
                        "energy": np.float32(energy),
                        "event_type": np.int32(labels_blk[local_j]),
                        "vertex_x": np.float32(pos_blk[local_j, 0]),
                        "vertex_y": np.float32(pos_blk[local_j, 1]),
                        "vertex_z": np.float32(pos_blk[local_j, 2]),
                        "particle_dir_x": np.float32(dir_blk[local_j, 0]),
                        "particle_dir_y": np.float32(dir_blk[local_j, 1]),
                        "particle_dir_z": np.float32(dir_blk[local_j, 2]),
                        "pmt_charge": charges.astype(np.float32),
                        "pmt_time": times.astype(np.float32),
                        "tube_ids": pmts.astype(np.int32),
                    }
                    writer.write_event(event_idx=written, **event_data)
                    written += 1

                indices_processed += len(chunk_idx)
                if done:
                    break

                hits_read += int(len(hit_charge_blk))
                runs_read += n_runs
                elapsed = time.time() - t0
                print(
                    f"[hy] chunk {chunk_no}/{n_chunks}: "
                    f"wrote {written} events so far "
                    f"(skipped keep={skipped_keep}, empty={skipped_empty}, "
                    f"cuts={skipped_cuts}) "
                    f"read {len(hit_charge_blk):,} hits in {n_runs} run(s) "
                    f"[{elapsed:.1f}s]"
                )

    with h5py.File(output_file, "a") as out:
        out.attrs["n_events"] = written

    dt = time.time() - t0
    print(
        f"[hy] done in {dt:.1f}s: wrote {written} events to {output_file} "
        f"(skipped keep={skipped_keep}, empty={skipped_empty}, cuts={skipped_cuts}, "
        f"{indices_processed} source indices processed)."
    )
    print(
        f"[hy] hit I/O: read {hits_read:,} hits in {runs_read:,} contiguous run(s) "
        f"(max_hit_gap={max_hit_gap})"
    )
    return {
        "input_file": str(input_file),
        "output_file": str(output_file),
        "events_written": written,
        "events_skipped_keep": skipped_keep,
        "events_skipped_empty": skipped_empty,
        "events_skipped_cuts": skipped_cuts,
        "source_indices_processed": indices_processed,
        "hits_read": hits_read,
        "hit_runs_read": runs_read,
        "elapsed_seconds": dt,
    }


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Convert WatChMaL flat Super-K .hy HDF5 to GhostHunter hierarchical HDF5.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--input", required=True, type=Path, help="Input flat .hy HDF5 path.")
    p.add_argument("--output", required=True, type=Path, help="Output hierarchical HDF5 path.")
    p.add_argument("--start", type=int, default=0, help="First source event index (default: 0).")
    p.add_argument(
        "--stop",
        type=int,
        default=None,
        help="Stop before this source event index (default: all events).",
    )
    p.add_argument("--step", type=int, default=1, help="Stride over source events (default: 1).")
    p.add_argument(
        "--keep-event-only",
        action="store_true",
        help="Skip events where keep_event[i] is False (if dataset present).",
    )
    p.add_argument(
        "--indices-npz",
        type=Path,
        default=None,
        help="NPZ with source row indices (default key: keep_event_idx).",
    )
    p.add_argument(
        "--indices-key",
        default="keep_event_idx",
        help="Array key inside --indices-npz (default: keep_event_idx).",
    )
    p.add_argument(
        "--max-events",
        type=int,
        default=None,
        help="Maximum events to write after filtering (first N passing).",
    )
    p.add_argument(
        "--min-hit-charge",
        type=float,
        default=0.11,
        help=(
            "Remove hits with pmt_charge strictly below this threshold (p.e.); "
            "time and tube_ids are masked the same way (default: 0.11; use 0 to disable)."
        ),
    )
    p.add_argument(
        "--max-hit-charge",
        type=_parse_max_hit_charge,
        default=51.0,
        help=(
            "Keep hits but cap pmt_charge at this value (p.e.) via np.clip; "
            "default: 51.0; pass 'none' to disable the cap."
        ),
    )
    p.add_argument(
        "--min-n-hits",
        type=int,
        default=None,
        help="Skip events with fewer hits after charge filter (Felix gt200Hits).",
    )
    p.add_argument(
        "--max-energy",
        type=float,
        default=None,
        help="Skip events with energies[i,0] above this value in MeV (Felix 2000MeVCut).",
    )
    p.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Source events per RAM-bounded read batch (default: 500; not SLURM output size).",
    )
    p.add_argument(
        "--max-hit-gap",
        type=int,
        default=4096,
        help=(
            "Merge hit reads of two selected events separated by fewer than this many "
            "hits, trading a little over-read for one fewer seek (default: 4096). "
            "0 reads strictly only the requested hits."
        ),
    )
    p.add_argument(
        "--start-event",
        type=int,
        default=None,
        help="First index in the ordered index list (after --indices-npz / --start..--stop).",
    )
    p.add_argument(
        "--num-events",
        type=int,
        default=None,
        help="Max entries from the index list starting at --start-event.",
    )
    p.add_argument(
        "--chunk-index",
        type=int,
        default=None,
        help="SLURM array task id: slice index list [i*N, (i+1)*N) with --events-per-chunk.",
    )
    p.add_argument(
        "--events-per-chunk",
        type=int,
        default=None,
        help="Index-list entries per output file when using --chunk-index (e.g. 5000).",
    )
    p.add_argument(
        "--compression",
        default="gzip",
        help="HDF5 compression for vector datasets (default: gzip).",
    )
    return p


if __name__ == "__main__":
    args = _build_argparser().parse_args()
    convert(
        input_file=args.input,
        output_file=args.output,
        start=args.start,
        stop=args.stop,
        step=args.step,
        keep_event_only=args.keep_event_only,
        max_events=args.max_events,
        chunk_size=args.chunk_size,
        max_hit_gap=args.max_hit_gap,
        compression=args.compression,
        indices_npz=args.indices_npz,
        indices_key=args.indices_key,
        min_hit_charge=args.min_hit_charge,
        max_hit_charge=args.max_hit_charge,
        min_n_hits=args.min_n_hits,
        max_energy=args.max_energy,
        start_event=args.start_event,
        num_events=args.num_events,
        chunk_index=args.chunk_index,
        events_per_chunk=args.events_per_chunk,
    )
