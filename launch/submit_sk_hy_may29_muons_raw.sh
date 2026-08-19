#!/bin/bash
# may29_2025 muons multi_combine.hy -> raw HDF5 chunks (no per-hit charge cuts).
# Stages .hy and chunk writes on /tmp (sk_hy_to_h5_slurm.sh). Concat skipped by default.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="/sps/t2k/eleblevec/Datasets/sk_iv/pgun_ccan/may29_2025_muons_pg_combine_1"
INPUT_HY="${DATA_DIR}/multi_combine.hy"
CHUNK_DIR="${DATA_DIR}/h5/chunks_raw"
OUTPUT_STEM="sk_may29_muons_pg_combine_raw"

if [[ ! -f "$INPUT_HY" ]]; then
    echo "ERROR: missing input .hy: $INPUT_HY" >&2
    exit 1
fi

source /sps/t2k/eleblevec/miniconda3/etc/profile.d/conda.sh
conda activate pt28_cuda129

N_INDICES=$(python3 -c "
import h5py
with h5py.File('${INPUT_HY}', 'r') as f:
    print(f['energies'].shape[0])
")
echo "n_events=${N_INDICES}"

export DATA_DIR
export INPUT_HY
export CHUNK_DIR="${CHUNK_DIR}"
export OUTPUT_H5_STEM="${CHUNK_DIR}/${OUTPUT_STEM}"
export FINAL_H5="${DATA_DIR}/h5/${OUTPUT_STEM}.h5"
export N_INDICES
export EVENTS_PER_CHUNK=5000
export STAGE_HY_TO_TMP=1
export SKIP_CONCAT="${SKIP_CONCAT:-1}"
export EXTRA_ARGS="--min-hit-charge 0 --max-hit-charge none"
unset INDICES_NPZ

"${SCRIPT_DIR}/submit_sk_hy_to_hdf5.sh"
