# State of `ntupleManager/`

Audit of `mini-Caverns-toolsbox/ntupleManager/` as of 2026-05-23.
Hierarchical-only cleanup applied 2026-05-23: all flat/chunked-flat producers,
converters, and configs were removed from this package. Flat-vs-hierarchical
benchmark code lives in `mini-Caverns-benchmarks/`.

---

## 1. Tree structure

```
ntupleManager/
├── root_to_hier_hdf5.py                # production: light ROOT ntuple -> hierarchical HDF5
├── clean_jobs.sh                       # housekeeping: drops dummy/empty job folders under jobs/
├── configs/                            # YAML data-extraction configs (see below)
│   ├── data_extraction_config_e-_train_val_set.yaml      # production (HyperK, e-, 1M train/val)
│   ├── data_extraction_config_e-_test_set.yaml           # production (HyperK, e-, 1M test)
│   ├── data_extraction_config_e-_hier_dummy.yaml         # smoke-test config for hier converter
│   ├── data_extraction_config_e-_WCTE_train_val_set.yaml # broken: old field-config schema
│   ├── data_extraction_config_e-_WCTE_test_set.yaml      # broken: old field-config schema
│   ├── data_extraction_config_WCTE_example.yaml          # broken: old field-config schema
│   ├── data_extraction_config_mu_train_val_set.yaml      # legacy/broken: old schema, stale paths
│   ├── data_extraction_config_mu_test_set.yaml           # legacy/broken: old schema, stale paths
│   ├── data_extraction_config_pi0_train_val_set.yaml     # legacy/broken: old schema, stale paths
│   └── data_extraction_config_small_dataset.yaml         # legacy/broken: old schema, debug-only
├── doc/                                # this folder
│   ├── EDGE_FORMAT_CHANGE_README.md            # records the Dec 2025 (N,2) edge axis flip
│   ├── GEOMETRY_MAPPING_README.md              # how geometry_mappings.py is meant to be used
│   ├── GEOMETRY_MAPPING_SUMMARY.md             # near-duplicate of the README above
│   ├── STATE_OF_NTUPLE_MANAGER.md              # (this file)
│   └── PIPELINES_OVERVIEW.md                   # (companion file)
├── jobs/                               # SLURM job archive (1 folder per submission)
├── launch/
│   ├── submit_root_to_hdf5.sh          # production: wrapper that creates a job dir then sbatch's
│   ├── root_to_hdf5_slurm.sh           # production: SLURM body (copy ROOT to /tmp, run, copy h5 back)
│   └── h5_read.sh                      # one-liner: `h5ls -r $1 | head -n 35`
├── make_ntuple_dataset/
│   ├── hadd_hierarchical_lib.sh                # reusable bash lib (multi-level hadd, scratch copy)
│   ├── Hyper-K_merge_and_separate_ntuple_as_train_val_test.sh # production (HK FD, 1..10000 folders)
│   └── WCTE_merge_and_separate_ntuple_as_train_val_test.sh    # production (WCTE-style folder layout)
└── utils/
    ├── geometry_mappings.py            # production: HyperK / WCTE name remap
    ├── hdf5_writer.py                  # production: `HDF5GraphWriter` (hierarchical, per-event group)
    ├── funct_utils.py                  # production: `load_config` / `print_summary` only
    └── data_check.ipynb                # notebook: visual sanity-check of HDF5 outputs
```

The `jobs/` folder grows linearly with submissions (75 entries, mostly `slurm_*.err/.out`); the
`clean_jobs.sh` script is the maintenance tool for it. There are **no** `*.bak`, `*_old.*`,
`*.orig`, `*_v0.*`, `*_v1.*`, `flat_dataset*.py`, `flat_hdf5*.py`, or stray `*.root` files inside
the package outside of `jobs/`.  No `.ipynb_checkpoints/` either.

---

## 2. Features (in production)

### 2.1 Light ROOT ntuple -> hierarchical HDF5
- **What:** chunked uproot read of a TTree (default `pure_root_tree`); one HDF5 group per kept event
  (`event_<idx>`), one dataset per field, gzip compression. Skips events with `n_digi_hits == 0`.
- **File:** `root_to_hier_hdf5.py`
- **Run:** `python root_to_hier_hdf5.py --config configs/data_extraction_config_e-_train_val_set.yaml`

### 2.2 Geometry name mapping HK <-> WCTE
- **What:** translates the `field_config` HDF5-standard names (e.g. `n_digi_hits`, `trigger_time`,
  `particle_dir`) to the per-detector ROOT branch names (HK uses identity; WCTE uses
  `n_hits` / `time_trigger` / `particleDir` / etc.). Missing fields produce a `UserWarning` and are
  skipped instead of crashing.
- **File:** `utils/geometry_mappings.py` (`GEOMETRY_MAPPINGS`, `apply_geometry_mapping`,
  `validate_loaded_data`, `get_geometry_mapping`).
- **Used by:** `root_to_hier_hdf5.py`.

### 2.3 Field selection / dropping
- **What:** the YAML key `field_config` is a flat list of HDF5-standard field names. Anything not
  in that list is not loaded from the ROOT file at all (`uproot.iterate(expressions=...)`).
- **Files:** any YAML in `configs/` that uses `field_config` (today: the four `e-_*` configs).
- **Caveat:** several older configs still use the deprecated `scalar_fields_config` /
  `vector_fields_config` schema; the current `root_to_hier_hdf5.py` ignores those and ends up loading
  the empty list (see Section 3).

### 2.4 Dataset merging + train/val/test splitting
- **What:** loops over per-job subdirectories holding `ntuple_cut_ed_<n>.root`, builds a file list,
  and calls a hierarchical `hadd` (multi-level to dodge file-descriptor limits) optionally staging
  inputs into `$TMPDIR` first.
- **Files:** `make_ntuple_dataset/Hyper-K_merge_and_separate_ntuple_as_train_val_test.sh`,
  `make_ntuple_dataset/WCTE_merge_and_separate_ntuple_as_train_val_test.sh`,
  shared library `make_ntuple_dataset/hadd_hierarchical_lib.sh`.
- **Run:** `bash make_ntuple_dataset/Hyper-K_merge_and_separate_ntuple_as_train_val_test.sh`
  (paths and ranges edited at the top of the script).

### 2.5 SLURM submission helpers
- **What:** `submit_root_to_hdf5.sh` creates a per-submission folder under `jobs/`, copies the YAML
  into it, and `sbatch`'s `root_to_hdf5_slurm.sh`. The slurm body stages the ROOT file to `/tmp`,
  runs `root_to_hier_hdf5.py`, then copies the HDF5 result back to the destination on `/sps/`.
- **Files:** `launch/submit_root_to_hdf5.sh`, `launch/root_to_hdf5_slurm.sh`.
- **Run:** `bash launch/submit_root_to_hdf5.sh configs/data_extraction_config_e-_train_val_set.yaml`

### 2.6 HDF5 writer abstraction
- **What:** `HDF5GraphWriter` opens an HDF5 file with a context manager, exposes
  `write_event(event_idx=i, **named_arrays)` (one group per event, scalars stored uncompressed,
  arrays stored with the configured compression codec), and `add_metadata(**kwargs)` for root
  attributes (source file, tree name, geometry, fields config).
- **File:** `utils/hdf5_writer.py`.
- **Used by:** `root_to_hier_hdf5.py` (only consumer today).

### 2.7 Job housekeeping
- **What:** `clean_jobs.sh` walks `jobs/`, deletes folders that are empty / contain only YAML /
  contain `dummy` in their name. Has a `--dry-run` mode.
- **File:** `clean_jobs.sh`.
- **Run:** `bash clean_jobs.sh --dry-run`

---

## 3. Removed flat legacy (2026-05-23)

Decision: **hierarchical-only** `ntupleManager`. Flat and chunked-flat producers,
post-processors, and smoke-test configs were deleted. Comparison/benchmark code
remains in `mini-Caverns-benchmarks/`.

| File | What it was | Removed |
|---|---|---|
| `root_to_chuncked_flat_hdf5.py` | Per-chunk CSR-style flat HDF5 shards | 2026-05-23 |
| `convert_hier_to_flat1Darrays.py` | Hier HDF5 → flat 1D arrays + `index_pointer` | 2026-05-23 |
| `convert_edge_to_flat.py` | Edge HDF5 → flat `(N,2)` buffer (events2graph companion) | 2026-05-23 |
| `configs/data_extraction_config_e-_chunked_flat_dummy.yaml` | Smoke-test config for chunked-flat converter | 2026-05-23 |
| `utils/funct_utils.py::load_data` | Eager uproot loader (superseded by inline chunked loader) | 2026-05-23 |
| `utils/funct_utils.py::decompose_vector_data` | Vector decomposition helper (inlined in hier converter) | 2026-05-23 |
| `__pycache__/` (root + `utils/`) | Stale bytecode cache | 2026-05-23 |

SLURM launch scripts (`launch/submit_root_to_hdf5.sh`, `launch/root_to_hdf5_slurm.sh`)
were simplified to call `root_to_hier_hdf5.py` only.

---

## 4. Deprecated / broken configs (still present)

| File | What it implements | Why it's broken | Recommendation |
|---|---|---|---|
| `configs/data_extraction_config_mu_train_val_set.yaml` | HyperK mu- 50-1500 MeV train/val. | Uses `scalar_fields_config` + `vector_fields_config`; current code reads `field_config` only. | **Archive** or rewrite. |
| `configs/data_extraction_config_mu_test_set.yaml` | Same for test split. | Same. | **Archive** or rewrite. |
| `configs/data_extraction_config_pi0_train_val_set.yaml` | Same for pi0. | Same. | **Archive** or rewrite. |
| `configs/data_extraction_config_small_dataset.yaml` | Debug config (200 events). | Same old schema; output points into `playground/`. | **Delete** or rewrite. |
| `configs/data_extraction_config_WCTE_example.yaml` | Pedagogical WCTE config. | Old schema; silently no-op. | **Rewrite** to `field_config`. |
| `configs/data_extraction_config_e-_WCTE_train_val_set.yaml` | WCTE-shaped e- input, `geometry: "HyperK"`. | Old schema + misleading name. | **Rename** + rewrite. |
| `configs/data_extraction_config_e-_WCTE_test_set.yaml` | Same for test split. | Same. | Same. |
| `utils/data_check.ipynb` | Manual HDF5 sanity-check notebook. | Not automated. | **Keep** if used. |
| `doc/GEOMETRY_MAPPING_SUMMARY.md` | Overlap with README. | ~80 % duplicate. | **Merge** into README. |
| `jobs/*` | SLURM run archive. | Many obsolete/dummy entries. | **Run** `clean_jobs.sh` periodically. |

There are **no** flat producers, `flat_hdf5*.py`, or stray `ntuple_cut_ed_*.root` files inside
the package today.

---

## 5. Remaining redundancies

| Pair | Note | Canonical |
|---|---|---|
| `doc/GEOMETRY_MAPPING_README.md` vs `doc/GEOMETRY_MAPPING_SUMMARY.md` | Same topic, ~80 % overlap. | **README**. |
| `configs/data_extraction_config_e-_WCTE_*` vs `configs/data_extraction_config_WCTE_example.yaml` | Three configs for WCTE-shaped e- ntuples, all on deprecated schema. | **One** rewritten to `field_config`. |
| `Hyper-K_merge_and_separate_ntuple_as_train_val_test.sh` vs `WCTE_merge_and_separate_ntuple_as_train_val_test.sh` | 95 % identical. | **Both** (intentional). |

---

## 6. Recommended next steps

- **Rewrite** the three WCTE configs and four mu/pi0/small configs to `field_config` schema, or archive.
- **Consolidate** `doc/GEOMETRY_MAPPING_README.md` and `doc/GEOMETRY_MAPPING_SUMMARY.md`.
- **Run** `clean_jobs.sh` and prune `jobs/`.

Production package after the 2026-05-23 flat cleanup:

```
ntupleManager/
├── root_to_hier_hdf5.py
├── configs/{e-_train_val,e-_test,e-_hier_dummy}.yaml + WCTE-fixed.yaml
├── launch/{submit_root_to_hdf5.sh,root_to_hdf5_slurm.sh}
├── make_ntuple_dataset/{Hyper-K,WCTE}_merge_and_separate_*.sh + hadd_hierarchical_lib.sh
├── utils/{geometry_mappings.py, hdf5_writer.py, funct_utils.py, data_check.ipynb}
├── doc/{STATE_OF_NTUPLE_MANAGER, PIPELINES_OVERVIEW, GEOMETRY_MAPPING, EDGE_FORMAT_CHANGE}.md
└── clean_jobs.sh
```

---

## 7. Per-feature health check

| Feature | File | Status | Test coverage | Notes |
|---|---|---|---|---|
| Light ntuple -> hier HDF5 | `root_to_hier_hdf5.py` | production | manual (jobs/) | Active path; hot path under `submit_root_to_hdf5.sh`. |
| Geometry name mapping | `utils/geometry_mappings.py` | production | manual (used by every job) | HyperK + WCTE; no SK entry yet. |
| HDF5 writer | `utils/hdf5_writer.py` | production | manual | Single class, single consumer. |
| `field_config` selection | `configs/*.yaml` (only `field_config` style) | production | manual | Old `scalar/vector_fields_config` configs silently no-op. |
| Dataset merge + split | `make_ntuple_dataset/*` | production | manual (logs in dataset folders) | HK + WCTE wrappers around shared lib. |
| SLURM submission | `launch/submit_root_to_hdf5.sh`, `launch/root_to_hdf5_slurm.sh` | production | manual | Hierarchical only since 2026-05-23. |
| `funct_utils.load_config` / `print_summary` | `utils/funct_utils.py` | production | manual | Helpers only (`load_data` / `decompose_vector_data` removed 2026-05-23). |
| Job housekeeping | `clean_jobs.sh`, `launch/h5_read.sh` | production | none | One-liners. |
| Sanity-check notebook | `utils/data_check.ipynb` | unused (manual) | notebook | Nothing automates it. |

---

## Surprises

1. **The "external" upstream extractor is in fact in this user's own tree.** The merge script
   (`make_ntuple_dataset/Hyper-K_merge_and_separate_*.sh`) reads from
   `/sps/t2k/eleblevec/Datasets/custom_wcsimroot_datasets/prod_HKFD_ben_1.12.20corr/...`, and the
   per-job scripts inside that dataset (`scripts/wcsimroot_to_root_execute.sh`,
   `scripts/root_explorer_execute.sh`) call:
     - `/sps/t2k/eleblevec/BigBrother/WCSimRootToRoot-home/1.12.20_corrBen/WCSimRootToRoot/bin/wcsimroot_to_root`
       — produces `ntuple_raw_*.root` (`pure_root_tree`).
     - `/sps/t2k/eleblevec/BigBrother/RootExplorer/bin/apply_cuts_clone`
       — produces `ntuple_cut_*.root`.
     - `/sps/t2k/eleblevec/BigBrother/RootExplorer/bin/compute_extra_data_clone`
       — produces `ntuple_cut_ed_*.root` (adds `dwall`, `towall`, ...).
   The chain is the user's own code (using Benjamin Quilain's WCSim build at
   `/sps/t2k/bquilain/HK/Reconstruction/official_2023/Gonzalo/WCSim-1.12.20/`). The new
   `rwcs2ntuple` collapses these three steps into one binary against `libWCSimRoot.so.1.12.22`.

2. **Several "WCTE" configs silently no-op.** All five `configs/*WCTE*.yaml` and three
   `mu_*` / `pi0_*` / `small_dataset` configs use `scalar_fields_config` / `vector_fields_config`
   keys, which the current `root_to_hier_hdf5.py` does **not** read (it reads `field_config`
   only, line 71). A run against any of those configs will produce a file containing only the
   metadata block.

3. **`data_extraction_config_e-_WCTE_*.yaml` says `geometry: "HyperK"`.** The inline comment claims
   "wcte corresponds mathieu's ntuple format, HyperK to mine" — these are HK-named ntuples produced
   from WCTE-shaped simulations. The filename is misleading.

4. **The hier-converter has a pile of commented-out code** (lines 186–290 of
   `root_to_hier_hdf5.py`): the previous non-iterator/eager implementation. Worth a clean-up pass.

5. **`__pycache__/convert_edge_to_flat.cpython-39.pyc` existed at the package root** — removed
   with the 2026-05-23 flat cleanup.

6. **`doc/GEOMETRY_MAPPING_SUMMARY.md` is not a strict subset of `GEOMETRY_MAPPING_README.md`** —
   it adds the per-field comparison table — but the prose duplicates 80 % of the README. Worth
   merging.
