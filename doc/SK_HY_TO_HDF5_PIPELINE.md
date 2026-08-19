# Super-K WatChMaL `.hy` → GhostHunter HDF5 pipeline

Convert WatChMaL **flat** Super-K HDF5 (`.hy`) into the **hierarchical** per-event layout used by GhostHunter (`event_<i>/n_digi_hits`, `pmt_charge`, `tube_ids`, …).

All conversions use a **two-stage chunked workflow**:

1. **Array jobs** (`sk_hy_to_h5`) — each task reads a slice of the index list from the flat `.hy` on `/sps` and writes one chunk HDF5.
2. **Concat job** (`sk_hy_to_h5_concat`) — merges chunk files into a single HDF5. Each chunk is **copied to `/tmp` before read**; the merged file is also built on `/tmp`, then moved to `/sps`.

There is **no monolithic** “convert the full `.hy` in one job” path.

---

## Prerequisites

**Environment (CC-IN2P3 / cc-lyon):**

```bash
source /sps/t2k/eleblevec/miniconda3/etc/profile.d/conda.sh
conda activate pt28_cuda129
```

**Typical inputs (pgun_ccan production):**

| Path | Description |
|------|-------------|
| `.../sk_iv/pgun_ccan/multi_combine.hy` | WatChMaL flat source (~119 GB) |
| `.../sk_iv/pgun_ccan/keep_event_indices.npz` | Event index list (`keep_event_idx`, ~3.82M rows) |
| `.../geometries/SK_geo_from_watchmal_website_gh_like.npz` | PMT geometry (used at training/plot time, not in HDF5) |

**Scripts** (under `ntupleManager/`):

| Script | Role |
|--------|------|
| `hy_flat_to_hier_hdf5.py` | Python converter (chunk mode via `--chunk-index`) |
| `utils/concat_hier_hdf5_chunks.py` | Merge chunk HDF5s |
| `launch/submit_sk_hy_to_hdf5.sh` | Submit array + concat |
| `launch/sk_hy_to_h5_slurm.sh` | SLURM array worker |
| `launch/submit_sk_hy_concat.sh` | Submit concat only |
| `launch/sk_hy_concat_slurm.sh` | SLURM concat worker |
| `launch/submit_sk_hy_smoke_1k.sh` | 1k-event smoke test |

---

## Per-hit charge cuts (baked into HDF5)

Default production cuts (set via `EXTRA_ARGS` in submit scripts):

| Cut | Value | Effect |
|-----|-------|--------|
| `--min-hit-charge` | **0.11** p.e. | Hit **removed** from `pmt_charge` / `pmt_time` / `tube_ids` |
| `--max-hit-charge` | **51.0** p.e. | Hit **kept**, charge capped at 51 |

Chunk and merged filenames include the range, e.g. `chunks_0.11_to_51_pe/`.

Optional **event-level** cuts (also via `EXTRA_ARGS`):

- `--min-n-hits 200`
- `--max-energy 2000`

---

## Quick start: smoke test (1k events)

```bash
cd /sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager/launch
./submit_sk_hy_smoke_1k.sh
```

This submits **one** array task (`EVENTS_PER_CHUNK=1000`, `N_INDICES=1000`) plus concat.

**Outputs:**

- Chunks: `.../smoke_datasets/chunks_0.11_to_51_pe/sk_pgun_ccan_smoke_chunk_00000.h5`
- Merged: `.../smoke_datasets/sk_pgun_ccan_1000evt.h5`

---

## Full production run (~3.82M keep_event events)

```bash
cd /sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager/launch
./submit_sk_hy_to_hdf5.sh
```

Defaults:

- **765 array tasks** (3_820_200 indices ÷ 5000 per task)
- Chunks: `.../h5/chunks_0.11_to_51_pe/sk_pgun_ccan_keep_event_chunk_*.h5`
- Merged: `.../h5/sk_pgun_ccan_keep_event_0.11_to_51_pe.h5`
- Concat starts automatically after all array tasks succeed (`afterok`)

**Monitor:**

```bash
squeue -u elebleve
sacct -j <ARRAY_JOB_ID> -X --format=JobID,State,ExitCode,Elapsed,MaxRSS
ls .../h5/chunks_0.11_to_51_pe/*.h5 | wc -l   # expect 765
tail -f .../logs/sk_hy_to_h5_concat_<JOBID>.out
```

---

## Environment overrides

All submit scripts respect these variables:

| Variable | Default | Meaning |
|----------|---------|---------|
| `DATA_DIR` | `.../sk_iv/pgun_ccan` | Dataset root |
| `INPUT_HY` | `${DATA_DIR}/multi_combine.hy` | Flat WatChMaL file |
| `INDICES_NPZ` | `${DATA_DIR}/keep_event_indices.npz` | Index NPZ |
| `EVENTS_PER_CHUNK` | `5000` | Indices per array task |
| `N_INDICES` | `3820200` | Total indices to process |
| `CHUNK_DIR` | `.../h5/chunks_0.11_to_51_pe` | Chunk output directory |
| `OUTPUT_H5_STEM` | `${CHUNK_DIR}/sk_pgun_ccan_keep_event` | Chunk filename stem |
| `FINAL_H5` | `.../h5/sk_pgun_ccan_keep_event_0.11_to_51_pe.h5` | Merged output |
| `EXTRA_ARGS` | `--min-hit-charge 0.11 --max-hit-charge 51.0` | Passed to converter |
| `SKIP_CONCAT` | `0` | Set to `1` to only submit the array |

**Small file / few events** — use a small `EVENTS_PER_CHUNK` and `N_INDICES`:

```bash
export N_INDICES=5000
export EVENTS_PER_CHUNK=1000   # → 5 array tasks
export CHUNK_DIR=/path/to/my_chunks
export FINAL_H5=/path/to/my_out.h5
./submit_sk_hy_to_hdf5.sh
```

---

## Concat only (chunks already on disk)

If the array finished but concat failed or was skipped:

```bash
cd .../ntupleManager/launch
./submit_sk_hy_concat.sh
```

Or with explicit paths:

```bash
export CHUNK_GLOB="/sps/.../chunks_0.11_to_51_pe/sk_pgun_ccan_keep_event_chunk_*.h5"
export OUTPUT_H5="/sps/.../h5/sk_pgun_ccan_keep_event_0.11_to_51_pe.h5"
./submit_sk_hy_concat.sh
```

Concat behaviour:

- Reads chunk list from `CHUNK_GLOB`
- **Stages each chunk to `/tmp/sk_hy_chunks_<jobid>/`** before `h5py` read, then deletes staged file
- Writes merged HDF5 to `/tmp/..._concat_<jobid>.h5`, then `mv` to `OUTPUT_H5`

---

## Manual CLI (no SLURM)

**One chunk** (array task 42):

```bash
cd .../ntupleManager
python hy_flat_to_hier_hdf5.py \
  --input  /sps/.../multi_combine.hy \
  --output /tmp/sk_stem.h5 \
  --indices-npz /sps/.../keep_event_indices.npz \
  --chunk-index 42 \
  --events-per-chunk 5000 \
  --chunk-size 500 \
  --min-hit-charge 0.11 \
  --max-hit-charge 51.0
# → /tmp/sk_stem_chunk_00042.h5 (move to chunk dir)
```

**Merge chunks:**

```bash
python utils/concat_hier_hdf5_chunks.py \
  --glob '/sps/.../chunks_0.11_to_51_pe/sk_pgun_ccan_keep_event_chunk_*.h5' \
  --output /tmp/merged.h5 \
  --stage-dir /tmp/my_chunk_stage \
  --progress-every 50000
```

---

## Output HDF5 layout

```text
/event_0/
    n_digi_hits         (int32)
    energy              (float32, MeV)
    event_type          (int32, WatChMaL class index, production-dependent -- see below)
    vertex_x/y/z        (float32, cm)
    particle_dir_x/y/z  (float32)
    pmt_charge          (float32[n_hits], p.e., after charge cuts)
    pmt_time            (float32[n_hits], ns)
    tube_ids            (int32[n_hits], 1-based SK tube IDs)
/event_1/
...
```

Root attrs include `n_events`, `min_hit_charge`, `max_hit_charge`, and concat provenance (`chunk_first`, `chunk_last`, `chunk_files` dataset for large merges).

**PMT positions** are not stored in the HDF5; resolve via geometry NPZ + `tube_ids` in GhostHunter.

---

## Resource estimates (full keep_event)

| Stage | Wall time | Memory | Disk |
|-------|-----------|--------|------|
| Array (765 tasks, parallel) | ~30 min – 2 h | **32G**/task (heaviest ~20 GB RSS) | ~**101 GB** chunks |
| Concat (single node) | ~**18–20 h** | ~16G | ~**100 GB** merged |

Concat throughput was ~55–60 events/s when reading chunks directly from `/sps`; staging chunks on `/tmp` should improve this.

SLURM limits: array tasks **2 h**, concat **24 h** (`sk_hy_concat_slurm.sh`). Increase concat time if needed.

---

## Troubleshooting

### Array task `OUT_OF_MEMORY`

Heavy events can exceed 16G. Workers request **32G** (`sk_hy_to_h5_slurm.sh`). Re-run failed task only:

```bash
export INPUT_HY=... OUTPUT_H5_STEM=... INDICES_NPZ=... EVENTS_PER_CHUNK=5000
export EXTRA_ARGS="--min-hit-charge 0.11 --max-hit-charge 51.0"
sbatch --array=509 launch/sk_hy_to_h5_slurm.sh
```

### Concat `DependencyNeverSatisfied`

One failed array task blocks concat. Fix the missing chunk, then resubmit concat (or cancel stuck concat job first).

### Concat `TIME LIMIT`

Merged file only appears after successful `mv` from `/tmp`. If concat times out, **no final HDF5 on `/sps`**. Resubmit `./submit_sk_hy_concat.sh` (chunks are reusable).

### Missing chunk in glob

```bash
ls .../chunks_0.11_to_51_pe/sk_pgun_ccan_keep_event_chunk_*.h5 | wc -l
# expect 765 for full production
```

### Inspect one event

```bash
python utils/inspect_hdf5_event.py --file /path/to/out.h5 --event 0
```

---

## WatChMaL label mapping (pgun)

Stored as-is in `event_type` (**not** PDG).  It is a WatChMaL *class index* and it is
**production-dependent** -- do not assume it.  For the SK-IV particle-gun production
`Datasets/sk_iv/pgun_ccan/` (`multi_combine.hy`) it is:

| `labels` in `.hy` | Particle | Min. total energy in the production |
|-------------------|----------|-------------------------------------|
| 0 | mu- | 159.92 MeV |
| 1 | e-  | 0.50 MeV |
| 2 | pi+ | 211.58 MeV |

Verified 2026-08-03: those minima are the water Cherenkov thresholds,
sqrt(120^2 + 105.66^2) = 159.92 for mu- and sqrt(159^2 + 139.57^2) = 211.58 for pi+.
`energies` is therefore **total** energy, rest mass included; and `event_ids` is *not*
the particle type -- it is the 0-based event id inside the source ROOT job (0..998).

To identify the mapping in a new production, histogram `energies` per label value: the
minimum of each is that particle's Cherenkov threshold.  `hy_flat_to_hier_hdf5.py` and
`utils/build_uniform_energy_indices.py` carry the same table.

An earlier revision of this document gave 0=gamma, 1=e, 2=mu.  That is the WatChMaL
tutorial ordering, not this production's, and using it mislabels every event.

Remap downstream if your training config expects PDG codes.

---

## Related docs

- [PIPELINES_OVERVIEW.md](PIPELINES_OVERVIEW.md) — all detector pipelines
- [README.md](../README.md) — ntupleManager overview
