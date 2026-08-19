# ntupleManager

Convert **light-ntuple** ROOT files (`pure_root_tree`) into **hierarchical HDF5** for [GhostHunter](https://github.com/thesis-RSA-code/GhostHunter) training and inference.

This package does **not** read raw WCSim `wcsim_output_*.root` files. That step lives upstream (`rwcs2ntuple`, WCSimRootToRoot, RootExplorer, etc.). Here we only consume ntuples that **uproot** can open (typically `ntuple_cut_ed_*.root` or WCTE v2 concatenated files).

## What it does

| Detector | Entry point | Geometry |
|----------|-------------|----------|
| HK FD (`HyperK`) | `root_to_hier_hdf5.py --config configs/...yaml` | `utils/geometry_mappings.py` maps HDF5 field names → ROOT branch names |
| WCTE v2 | `root_to_hier_hdf5_wcte.py` (or `--detector WCTE` on the HK script) | Inline branch mapping in `root_to_hier_hdf5_wcte.py` |
| Super-K WatChMaL flat `.hy` | `hy_flat_to_hier_hdf5.py` | Flat HDF5 (`event_hits_index` + jagged hits) → same hierarchical layout; `geometry: SK` |

**Output layout:** one HDF5 group per kept event:

```text
/event_<i>/
    n_digi_hits, energy, event_type, trigger_time, ...
    vertex_x, vertex_y, vertex_z, ...
    hitx, hity, hitz, pmt_charge, pmt_time, tube_ids, ...
```

Events with `n_digi_hits == 0` are skipped. WCTE uses contiguous indices (`event_0` …); HK may leave gaps indexed by global event number.

## Requirements

- Python 3.10+
- `h5py`, `numpy`, `awkward`, `uproot`, `tqdm`, `pyyaml`, `psutil`
- Optional: `ROOT` C++ bindings only for legacy paths outside this repo

Example environment on CC-IN2P3:

```bash
module load Analysis ROOT
conda activate pt28_cuda129   # or your env with the packages above
```

## Quick start

### HK (YAML-driven)

1. Copy and edit a config under `configs/` (`input_file`, `output_file`, `tree_name`, field lists).
2. Run:

```bash
cd ntupleManager
python root_to_hier_hdf5.py --config configs/data_extraction_config_small_dataset.yaml
```

### WCTE v2 (CLI)

```bash
python root_to_hier_hdf5_wcte.py \
  --input  /path/to/wcte_light_ntuple.root \
  --output /path/to/wcte_out.h5 \
  --tree-name pure_root_tree
```

Or via the unified driver:

```bash
python root_to_hier_hdf5.py --detector WCTE --config configs/data_extraction_config_WCTE_example.yaml
```

### Super-K WatChMaL flat `.hy`

See **[doc/SK_HY_TO_HDF5_PIPELINE.md](doc/SK_HY_TO_HDF5_PIPELINE.md)** for the full chunked SLURM workflow, charge cuts, concat staging, and troubleshooting.

#### Chunked CLI (manual)

All production conversions use **chunked** array jobs + concat (never a single monolithic pass over the full `.hy`).

```bash
# One array task (smoke / small subset)
python hy_flat_to_hier_hdf5.py \
  --input /path/to/multi_combine.hy \
  --output /path/to/stem.h5 \
  --indices-npz /path/to/keep_event_indices.npz \
  --chunk-index 0 --events-per-chunk 1000 \
  --min-hit-charge 0.11 --max-hit-charge 51.0

# Merge chunks
python utils/concat_hier_hdf5_chunks.py \
  --glob '/path/to/chunks/stem_chunk_*.h5' \
  --output /path/to/sk_out.h5
```

Inspect one event:

```bash
python utils/inspect_hdf5_event.py --file /path/to/out.h5 --event 0
```

## SLURM (CC-IN2P3)

Edit paths at the top of the submit wrappers, then:

```bash
./launch/submit_root_to_hdf5.sh configs/data_extraction_config_e-_train_val_set.yaml
./launch/submit_wcte_root_to_hdf5.sh configs/data_extraction_config_WCTE_example.yaml
./launch/submit_hkfd_elneg_root_to_hdf5.sh   # HK FD production-style job
./launch/submit_sk_hy_to_hdf5.sh             # Super-K .hy: chunk array + concat
./launch/submit_sk_hy_smoke_1k.sh            # 1k-event smoke (1 chunk)
```

Worker scripts: `launch/root_to_hdf5_slurm.sh`, `launch/wcte_root_to_hdf5_slurm.sh`, `launch/sk_hy_to_h5_slurm.sh`, `launch/sk_hy_concat_slurm.sh`.  
Each run creates a timestamped folder under `jobs/` (gitignored).

Clean old job dirs: `./clean_jobs.sh`

## Geometry files

PMT positions and tube-id tables are **not** stored in this repo. They live in GhostHunter, e.g. `extra_data/wcte_mpmt_pmts.npz` and HK geometry NPZ files. See `doc/GEOMETRY_MAPPING_README.md`.

## Upstream ntuple prep

`make_ntuple_dataset/` holds shell helpers to merge/split HK and WCTE ntuples into train/val/test ROOT files before conversion.

## Documentation

- [doc/PIPELINES_OVERVIEW.md](doc/PIPELINES_OVERVIEW.md) — full ROOT → HDF5 → GhostHunter pipelines (HK FD, WCTE, benchmarks)
- [doc/SK_HY_TO_HDF5_PIPELINE.md](doc/SK_HY_TO_HDF5_PIPELINE.md) — Super-K WatChMaL `.hy` chunked conversion (SLURM, charge cuts, concat)
- [doc/STATE_OF_NTUPLE_MANAGER.md](doc/STATE_OF_NTUPLE_MANAGER.md) — component status
- [doc/GEOMETRY_MAPPING_README.md](doc/GEOMETRY_MAPPING_README.md) — HK field mapping details

## Layout

```text
root_to_hier_hdf5.py      # HK + WCTE dispatcher (YAML for HK)
root_to_hier_hdf5_wcte.py # WCTE v2 dedicated converter
hy_flat_to_hier_hdf5.py   # WatChMaL flat Super-K .hy converter
utils/                    # HDF5 writer, geometry map, helpers
configs/                  # Example YAML extraction configs
launch/                   # SLURM submit + worker scripts
make_ntuple_dataset/      # Merge/split ntuples (pre-conversion)
doc/                      # Pipeline and geometry notes
```

## Related repos

- **GhostHunter** — consumes hierarchical HDF5
- **rwcs2ntuple** / WCSimRootToRoot — raw WCSim → light ntuple (upstream of this tool)
