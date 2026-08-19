#!/usr/bin/env python3
"""Build named boolean event masks from hierarchical HDF5 using a YAML cut config.

Output is a single ``cuts.npz`` with one boolean array per cut (length ``n_events``),
optional combined masks, and provenance metadata (YAML path/content, creation time).

Example::

    python utils/build_hdf5_cut_masks.py \\
        --config configs/wcte_cut_masks_example.yaml

NPZ layout::

    fiducial=[T,F,...], nhits10=[...], good=[...]   # boolean masks
    yaml_path, yaml_content, created_utc, hdf5_path   # object-dtype strings
    n_events, cut_names, combine_names              # scalars / object arrays

Combining cuts in downstream code: ``mask = cuts["fiducial"] & cuts["nhits10"]``.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

_OPS = frozenset({"gt", "ge", "lt", "le", "eq", "ne", "between", "in"})


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def _event_count(h5: h5py.File, prefix: str) -> int:
    for attr in ("n_events", "num_events", "n_event"):
        if attr in h5.attrs:
            return int(h5.attrs[attr])
    keys = [k for k in h5.keys() if k.startswith(prefix)]
    if not keys:
        raise ValueError(f"No groups matching prefix '{prefix}' in HDF5")
    indices = sorted(int(k[len(prefix) :]) for k in keys)
    if indices != list(range(len(indices))):
        raise ValueError(
            f"Non-contiguous event indices for prefix '{prefix}' "
            f"(found {len(indices)} groups, max index {max(indices)})"
        )
    return len(indices)


def _read_scalar(ev: h5py.Group, field: str) -> float | int:
    if field not in ev:
        raise KeyError(f"Field '{field}' not in event group (keys: {list(ev.keys())})")
    ds = ev[field]
    if ds.shape != ():
        raise ValueError(f"Field '{field}' is not a scalar (shape {ds.shape})")
    return ds[()]


def _read_field_value(ev: h5py.Group, field: str) -> float | int:
    """Read scalar field or array length when field names a 1-D hit array."""
    if field in ev:
        ds = ev[field]
        if ds.shape == ():
            return ds[()]
        return int(ds.shape[0])
    raise KeyError(f"Field '{field}' not in event group (keys: {list(ev.keys())})")


def _apply_op(value: float | int, op: str, threshold: Any) -> bool:
    if op == "gt":
        return value > threshold
    if op == "ge":
        return value >= threshold
    if op == "lt":
        return value < threshold
    if op == "le":
        return value <= threshold
    if op == "eq":
        return value == threshold
    if op == "ne":
        return value != threshold
    if op == "between":
        lo, hi = threshold
        return lo <= value <= hi
    if op == "in":
        return value in threshold
    raise ValueError(f"Unknown op '{op}'")


def _eval_cut(ev: h5py.Group, spec: dict[str, Any]) -> bool:
    field = spec["field"]
    op = spec.get("op", "ge")
    if op not in _OPS:
        raise ValueError(f"Unsupported op '{op}' (allowed: {sorted(_OPS)})")
    value = spec.get("value")
    if value is None and op not in ("eq", "ne"):
        raise ValueError(f"Cut on '{field}' missing 'value'")
    raw = _read_field_value(ev, field)
    return _apply_op(raw, op, value)


def _build_masks(
    h5_path: Path,
    cuts: dict[str, dict[str, Any]],
    *,
    event_prefix: str = "event_",
    progress_every: int = 100_000,
) -> tuple[dict[str, np.ndarray], int]:
    masks: dict[str, list[bool]] = {name: [] for name in cuts}
    n_events = 0

    with h5py.File(h5_path, "r") as h5:
        n_events = _event_count(h5, event_prefix)
        t0 = time.perf_counter()
        for i in range(n_events):
            ev = h5[f"{event_prefix}{i}"]
            for name, spec in cuts.items():
                masks[name].append(_eval_cut(ev, spec))
            if progress_every and (i + 1) % progress_every == 0:
                elapsed = time.perf_counter() - t0
                rate = (i + 1) / elapsed if elapsed > 0 else 0.0
                print(f"[masks] {i + 1}/{n_events} events ({rate:.0f} evt/s)", flush=True)

    return {name: np.asarray(vals, dtype=bool) for name, vals in masks.items()}, n_events


def _combine_masks(
    masks: dict[str, np.ndarray],
    combine: dict[str, list[str]],
) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    for combo_name, cut_names in combine.items():
        if not cut_names:
            raise ValueError(f"combine.{combo_name}: empty cut list")
        combo = np.ones(len(next(iter(masks.values()))), dtype=bool)
        for cut_name in cut_names:
            if cut_name not in masks:
                raise KeyError(
                    f"combine.{combo_name} references unknown cut '{cut_name}' "
                    f"(defined: {list(masks)})"
                )
            combo &= masks[cut_name]
        out[combo_name] = combo
    return out


def build_from_config(
    config_path: Path,
    *,
    output_path: Path | None = None,
    hdf5_path_override: Path | None = None,
    progress_every: int = 100_000,
) -> Path:
    config_path = config_path.resolve()
    cfg = _load_yaml(config_path)
    yaml_content = config_path.read_text(encoding="utf-8")

    hdf5_path_meta = Path(cfg["hdf5_path"])
    hdf5_path = Path(hdf5_path_override or hdf5_path_meta)
    if not hdf5_path.is_file():
        raise FileNotFoundError(f"HDF5 not found: {hdf5_path}")

    cuts = cfg.get("cuts")
    if not cuts:
        raise ValueError("Config must define a non-empty 'cuts' mapping")

    event_prefix = cfg.get("event_prefix", "event_")
    out_path = Path(output_path or cfg.get("output") or config_path.with_suffix(".npz"))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    masks, n_events = _build_masks(
        hdf5_path, cuts, event_prefix=event_prefix, progress_every=progress_every
    )

    combined = cfg.get("combine") or {}
    combo_masks = _combine_masks(masks, combined) if combined else {}

    created_utc = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {}
    payload.update(masks)
    payload.update(combo_masks)
    payload["yaml_path"] = np.array(str(config_path), dtype=object)
    payload["yaml_content"] = np.array(yaml_content, dtype=object)
    payload["created_utc"] = np.array(created_utc, dtype=object)
    payload["hdf5_path"] = np.array(str(hdf5_path_meta.resolve()), dtype=object)
    if hdf5_path_override is not None:
        payload["hdf5_staged_from"] = np.array(str(hdf5_path.resolve()), dtype=object)
    payload["n_events"] = np.array(n_events, dtype=np.int64)
    payload["cut_names"] = np.array(list(cuts.keys()), dtype=object)
    if combined:
        payload["combine_names"] = np.array(list(combined.keys()), dtype=object)

    np.savez_compressed(out_path, **payload)

    for name, mask in masks.items():
        print(f"  {name}: {int(mask.sum())}/{n_events} pass ({100.0 * mask.mean():.2f}%)")
    for name, mask in combo_masks.items():
        print(f"  {name} (combined): {int(mask.sum())}/{n_events} pass")

    print(f"Wrote {out_path} ({n_events} events, {len(masks)} cuts)")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build named boolean event masks from hierarchical HDF5 + YAML cuts."
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="YAML cut configuration (see configs/wcte_cut_masks_example.yaml)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output .npz path (overrides config 'output')",
    )
    parser.add_argument(
        "--hdf5",
        type=Path,
        default=None,
        help="HDF5 path (overrides config 'hdf5_path')",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=100_000,
        help="Print progress every N events (0 to disable)",
    )
    args = parser.parse_args(argv)

    build_from_config(
        args.config,
        output_path=args.output,
        hdf5_path_override=args.hdf5,
        progress_every=args.progress_every,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
