#!/bin/bash
# Submit chunked SK conversions for mu-, e-, pi+ (one array + concat per particle).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="/sps/t2k/eleblevec/Datasets/sk_iv/pgun_ccan"
INPUT_HY="${BASE}/combined_e-_mu-_pi+/multi_combine.hy"
KEEP_NPZ="${BASE}/combined_e-_mu-_pi+/keep_event_indices.npz"

if [[ ! -f "$INPUT_HY" ]]; then
    echo "ERROR: missing input .hy: $INPUT_HY" >&2
    exit 1
fi

source /sps/t2k/eleblevec/miniconda3/etc/profile.d/conda.sh
conda activate pt28_cuda129

echo "Building per-particle event_indices.npz from keep_event blocks..."
python << PY
import numpy as np
from pathlib import Path

base = Path("${BASE}")
keep = np.load("${KEEP_NPZ}")["keep_event_idx"]
slices = {
    "mu_neg":   keep[0:1273400],
    "electron": keep[1273400:2546800],
    "pi_pos":   keep[2546800:3820200],
}
for name, idx in slices.items():
    d = base / name
    for sub in ("logs", "h5", "h5/chunks_0.11_pe", "smoke_datasets"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    out = d / "event_indices.npz"
    np.savez_compressed(out, event_idx=idx.astype(np.int64), n_events=len(idx),
                        source_file="${INPUT_HY}", particle_folder=name)
    print(f"  {name}: {len(idx):,} indices -> {out}")
PY

declare -A STEM=(
    [mu_neg]=sk_pgun_ccan_mu-
    [electron]=sk_pgun_ccan_e-
    [pi_pos]=sk_pgun_ccan_pi+
)

N_EVENTS=1273400

for particle in mu_neg electron pi_pos; do
    DATA_DIR="${BASE}/${particle}"
    export DATA_DIR
    export INPUT_HY
    export INDICES_NPZ="${DATA_DIR}/event_indices.npz"
    export INDICES_KEY=event_idx
    export N_INDICES=${N_EVENTS}
    export CHUNK_DIR="${DATA_DIR}/h5/chunks_0.11_pe"
    export OUTPUT_H5_STEM="${CHUNK_DIR}/${STEM[$particle]}"
    export FINAL_H5="${DATA_DIR}/h5/${STEM[$particle]}_0.11_pe.h5"
    export EXTRA_ARGS="--min-hit-charge 0.11 --max-hit-charge none"
    export STAGE_HY_TO_TMP=1

    echo ""
    echo "========== ${particle} =========="
    "${SCRIPT_DIR}/submit_sk_hy_to_hdf5.sh"
done
