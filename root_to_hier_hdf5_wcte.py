"""
WCTE-v2 light-ntuple -> hierarchical HDF5 (HK FD compatible).

Reads `pure_root_tree` from a WCTE-v2-style ROOT file (the camelCase schema
produced by Mathieu Férey's upstream extractor; see
`doc/PIPELINES_OVERVIEW.md`, Pipeline C) and writes a per-event HDF5 in the
same hierarchical schema as the HK FD pipelines:

    /event_<i>/
        n_digi_hits         (scalar int32)
        energy              (scalar float32, MeV)
        event_type          (scalar int32,  PDG)
        trigger_time        (scalar float32, ns)
        vertex_{x,y,z}      (scalar float32, cm  -- z = cylinder axis)
        particle_dir_{x,y,z}     (scalar float32, unit vec)
        particle_stop_{x,y,z}    (scalar float32, cm)
        hitx, hity, hitz    (1-D float32 [n_digi_hits], cm  -- z = cyl axis)
        pmt_charge          (1-D float32 [n_digi_hits], p.e.)
        pmt_time            (1-D float32 [n_digi_hits], ns)
        tube_ids            (1-D int32   [n_digi_hits], 1..1843, indexes the
                             WCTE PMT geometry NPZ at
                             `GhostHunter/extra_data/wcte_mpmt_pmts.npz`)
        mPMT_tube_ids       (1-D int32   [n_digi_hits], 1..n_mPMT,  -- the
                             mPMT-module id of each hit; WCTE-specific)

Compared with the generic `root_to_hier_hdf5.py`:
- Does NOT route through `utils.geometry_mappings.apply_geometry_mapping`.
  That code path has confused name semantics (keys/values swapped) and the
  WCTE entry is missing tube_ids rows; fixing it would touch the production
  HK path, which we explicitly avoid.
- Indexes written events sequentially (`event_0..event_<n_written-1>`) so
  that the HDF5 has no gaps. `root_to_hier_hdf5.py` indexes by global event
  number, which leaves holes when `n_digi_hits == 0` events are skipped.

Fields intentionally NOT written (absent in the WCTE v2 ntuple):
    particle_start*

Run:
    python root_to_hier_hdf5_wcte.py \
        --input  /.../wcte_e-_uni_iso_FC_0-1000MeV_1k.root \
        --output /.../wcte_e-_1k.h5
"""

import argparse
import time
from pathlib import Path
from typing import Iterable, Tuple

import awkward as ak
import h5py
import numpy as np
import uproot
from tqdm import tqdm

try:
    from utils.hdf5_writer import HDF5GraphWriter
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from utils.hdf5_writer import HDF5GraphWriter


WCTE_SCALAR_BRANCHES = (
    "eventType", "n_hits", "energy", "time_trigger", "dwall", "towall",
)
WCTE_VECTOR_BRANCHES = ("vertex", "particleDir", "particleStop")
WCTE_HIT_BRANCHES = (
    "tubeIds", "mPMTtubeIds", "charge", "time", "hitx", "hity", "hitz",
)
ALL_WCTE_BRANCHES = WCTE_SCALAR_BRANCHES + WCTE_VECTOR_BRANCHES + WCTE_HIT_BRANCHES


WCTE_TO_HDF5_SCALAR = {
    "n_hits":       "n_digi_hits",
    "energy":       "energy",
    "eventType":    "event_type",
    "time_trigger": "trigger_time",
    "dwall":        "dwall",
    "towall":       "towall",
}

WCTE_TO_HDF5_VECTOR_COMPONENTS = {
    "vertex":       ("vertex_x", "vertex_y", "vertex_z"),
    "particleDir":  ("particle_dir_x", "particle_dir_y", "particle_dir_z"),
    "particleStop": ("particle_stop_x", "particle_stop_y", "particle_stop_z"),
}

WCTE_TO_HDF5_HIT = {
    "hitx":        "hitx",
    "hity":        "hity",
    "hitz":        "hitz",
    "charge":      "pmt_charge",
    "time":        "pmt_time",
    "tubeIds":     "tube_ids",
    "mPMTtubeIds": "mPMT_tube_ids",
}

WCTE_INT32_HIT_FIELDS = frozenset({"tube_ids", "mPMT_tube_ids"})


def _ensure_int32_ids(arr: np.ndarray) -> np.ndarray:
    """Return tube/mPMT id arrays as int32.

    The WCTE 3M concatenated ROOT declares ``tubeIds`` / ``mPMTtubeIds`` as
    ``float[]`` while the on-disk bytes are ``int32`` (uproot then yields tiny
    denormal floats). Reinterpret those bytes; leave correctly typed int32 as-is.
    """
    if arr.dtype == np.int32:
        return arr
    if arr.dtype == np.float32:
        return arr.view(np.int32)
    return arr.astype(np.int32)


def _check_wcte_schema(tree: "uproot.behaviors.TTree.TTree", verbose: bool = True) -> None:
    """Verify that the input tree has the WCTE v2 branches we expect."""
    present = set(tree.keys())
    missing = [b for b in ALL_WCTE_BRANCHES if b not in present]
    if missing:
        raise RuntimeError(
            f"Input tree is missing expected WCTE-v2 branches: {missing}. "
            f"Found branches: {sorted(present)}"
        )
    if verbose:
        print(f"[wcte] schema check OK ({len(ALL_WCTE_BRANCHES)} branches present).")


def _iter_chunks(
    file_path: Path,
    tree_name: str,
    step_size: str,
) -> Tuple[Iterable, int, "uproot.reading.ReadOnlyFile"]:
    """Open the ROOT file and return (chunk iterator, total entries, file handle)."""
    handle = uproot.open(str(file_path))
    tree = handle[tree_name]
    _check_wcte_schema(tree, verbose=True)
    total = tree.num_entries
    chunks = tree.iterate(list(ALL_WCTE_BRANCHES), step_size=step_size, library="ak")
    return chunks, total, handle


def convert(
    input_file: Path,
    output_file: Path,
    tree_name: str = "pure_root_tree",
    step_size: str = "200MB",
    compression: str = "gzip",
    max_events: int | None = None,
) -> dict:
    """Run the WCTE -> hierarchical HDF5 conversion. Returns a small stats dict."""
    if not input_file.exists():
        raise FileNotFoundError(f"Input ROOT file not found: {input_file}")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    chunks, total_events, root_handle = _iter_chunks(input_file, tree_name, step_size)

    fields_config = {
        **WCTE_TO_HDF5_SCALAR,
        **{k: list(v) for k, v in WCTE_TO_HDF5_VECTOR_COMPONENTS.items()},
        **WCTE_TO_HDF5_HIT,
    }
    skipped_empty = 0
    written = 0
    t0 = time.time()

    with HDF5GraphWriter(output_file, compression=compression) as writer:
        writer.add_metadata(
            source_file=str(input_file),
            tree_name=tree_name,
            geometry="WCTE",
            fields_config=str(fields_config),
            converter="root_to_hier_hdf5_wcte.py",
        )

        with tqdm(total=total_events, desc="WCTE events") as pbar:
            for chunk in chunks:
                for event in chunk:
                    pbar.update(1)
                    if max_events is not None and written >= max_events:
                        continue

                    n_hits = int(event["n_hits"])
                    if n_hits == 0:
                        skipped_empty += 1
                        continue

                    event_data: dict[str, np.ndarray] = {}
                    for wcte_name, hdf5_name in WCTE_TO_HDF5_SCALAR.items():
                        event_data[hdf5_name] = ak.to_numpy(event[wcte_name])

                    for wcte_name, components in WCTE_TO_HDF5_VECTOR_COMPONENTS.items():
                        vec = ak.to_numpy(event[wcte_name])
                        if vec.shape[-1] != 3:
                            raise ValueError(
                                f"Expected 3-component vector for '{wcte_name}', got shape {vec.shape}"
                            )
                        for i, comp_name in enumerate(components):
                            event_data[comp_name] = vec[..., i]

                    for wcte_name, hdf5_name in WCTE_TO_HDF5_HIT.items():
                        hits = ak.to_numpy(event[wcte_name])
                        if hits.shape[0] != n_hits:
                            raise ValueError(
                                f"'{wcte_name}' has length {hits.shape[0]} but n_hits={n_hits}"
                            )
                        if hdf5_name in WCTE_INT32_HIT_FIELDS:
                            hits = _ensure_int32_ids(hits)
                        event_data[hdf5_name] = hits

                    writer.write_event(event_idx=written, **event_data)
                    written += 1

    root_handle.close()
    dt = time.time() - t0
    print(
        f"[wcte] done in {dt:.1f}s: wrote {written} events, "
        f"skipped {skipped_empty} empty (read {total_events} total)."
    )
    return {
        "input_file": str(input_file),
        "output_file": str(output_file),
        "events_written": written,
        "events_skipped_empty": skipped_empty,
        "events_total_in_tree": total_events,
        "elapsed_seconds": dt,
    }


DEFAULT_INPUT_FILE = Path(
    "/sps/t2k/eleblevec/mini-Caverns-toolsbox/datasets/wcte_check_plots/"
    "wcte_e-_uni_iso_FC_0-1000MeV_1k.root"
)
DEFAULT_GEOMETRY_NPZ = Path(
    "/sps/t2k/eleblevec/mini-Caverns-toolsbox/GhostHunter/extra_data/wcte_mpmt_pmts.npz"
)


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--detector",
        choices=("WCTE",),
        default="WCTE",
        help="Detector schema (only WCTE is implemented here; use root_to_hier_hdf5.py for HK).",
    )
    p.add_argument("--input", "--input-file", dest="input_file", type=Path,
                   default=DEFAULT_INPUT_FILE,
                   help=f"WCTE v2 ROOT file (default: {DEFAULT_INPUT_FILE})")
    p.add_argument("--output", "--output-file", dest="output_file", type=Path,
                   required=True, help="Output HDF5 file path.")
    p.add_argument("--tree-name", default="pure_root_tree",
                   help="ROOT TTree to read (default: pure_root_tree).")
    p.add_argument("--step-size", default="200MB",
                   help="uproot.iterate step size (default: 200MB).")
    p.add_argument("--compression", default="gzip",
                   help="HDF5 compression codec (default: gzip).")
    p.add_argument("--max-events", type=int, default=None,
                   help="Cap on events written (debug).")
    return p


if __name__ == "__main__":
    args = _build_argparser().parse_args()
    convert(
        input_file=args.input_file,
        output_file=args.output_file,
        tree_name=args.tree_name,
        step_size=args.step_size,
        compression=args.compression,
        max_events=args.max_events,
    )
