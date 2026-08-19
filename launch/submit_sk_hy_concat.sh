#!/bin/bash
# Submit merge job for sk_hy_to_h5 chunks (optionally after array job completes).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${DATA_DIR:-/sps/t2k/eleblevec/Datasets/sk_iv/pgun_ccan}"
LOG_DIR="${LOG_DIR:-${DATA_DIR}/logs}"
CHUNK_DIR="${CHUNK_DIR:-${DATA_DIR}/h5/chunks_0.11_to_51_pe}"
mkdir -p "${LOG_DIR}" "$(dirname "${OUTPUT_H5:-${DATA_DIR}/h5/sk_pgun_ccan_keep_event_0.11_to_51_pe.h5}")"

CHUNK_GLOB="${CHUNK_GLOB:-${CHUNK_DIR}/sk_pgun_ccan_keep_event_chunk_*.h5}"
OUTPUT_H5="${OUTPUT_H5:-${DATA_DIR}/h5/sk_pgun_ccan_keep_event_0.11_to_51_pe.h5}"
export CHUNK_GLOB OUTPUT_H5

DEP_ARGS=()
if [ "${1:-}" != "" ]; then
    DEP_ARGS=(--dependency="afterok:$1")
    echo "Concat will run after array job $1 completes successfully."
fi

JOB_ID=$(sbatch \
    "${DEP_ARGS[@]}" \
    --output="${LOG_DIR}/sk_hy_to_h5_concat_%j.out" \
    --error="${LOG_DIR}/sk_hy_to_h5_concat_%j.err" \
    "${SCRIPT_DIR}/sk_hy_concat_slurm.sh" \
    | awk '{print $NF}')

echo "Submitted concat job ${JOB_ID}"
echo "  chunks: ${CHUNK_GLOB}"
echo "  output: ${OUTPUT_H5}"
