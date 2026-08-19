#!/bin/bash
# Submit chunked SK conversions for mu-, e-, pi+ using ALL events per label
# (no keep_event filter). Does not overwrite keep_event-filtered outputs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="/sps/t2k/eleblevec/Datasets/sk_iv/pgun_ccan"
INPUT_HY="${BASE}/combined_e-_mu-_pi+/multi_combine.hy"

if [[ ! -f "$INPUT_HY" ]]; then
    echo "ERROR: missing input .hy: $INPUT_HY" >&2
    exit 1
fi

source /sps/t2k/eleblevec/miniconda3/etc/profile.d/conda.sh
conda activate pt28_cuda129

echo "Building per-particle event_indices_all.npz (all rows per label)..."
python << PY
import h5py
import numpy as np
from pathlib import Path

hy = "${INPUT_HY}"
base = Path("${BASE}")
with h5py.File(hy, "r") as f:
    labels = f["labels"][:]

for lab, name, folder in [(0, "mu-", "mu_neg"), (1, "e-", "electron"), (2, "pi+", "pi_pos")]:
    idx = np.flatnonzero(labels == lab).astype(np.int64)
    d = base / folder
    (d / "h5/chunks_0.11_all").mkdir(parents=True, exist_ok=True)
    out = d / "event_indices_all.npz"
    np.savez_compressed(
        out, event_idx=idx, n_events=len(idx), source_file=hy, particle=name, filter="all_labels_no_keep"
    )
    print(f"  {name}: {len(idx):,} indices -> {out}")
PY

declare -A STEM=(
    [mu_neg]=sk_pgun_ccan_mu-
    [electron]=sk_pgun_ccan_e-
    [pi_pos]=sk_pgun_ccan_pi+
)
declare -A N_EVENTS=(
    [mu_neg]=1412486
    [electron]=1997999
    [pi_pos]=1915190
)

for particle in mu_neg electron pi_pos; do
    DATA_DIR="${BASE}/${particle}"
    export DATA_DIR
    export INPUT_HY
    export INDICES_NPZ="${DATA_DIR}/event_indices_all.npz"
    export INDICES_KEY=event_idx
    export N_INDICES=${N_EVENTS[$particle]}
    export CHUNK_DIR="${DATA_DIR}/h5/chunks_0.11_all"
    export OUTPUT_H5_STEM="${CHUNK_DIR}/${STEM[$particle]}"
    export FINAL_H5="${DATA_DIR}/h5/${STEM[$particle]}_all.h5"
    export EXTRA_ARGS="--min-hit-charge 0.11 --max-hit-charge none"
    export STAGE_HY_TO_TMP=1

    echo ""
    echo "========== ${particle} (all events) =========="
    "${SCRIPT_DIR}/submit_sk_hy_to_hdf5.sh"
done
