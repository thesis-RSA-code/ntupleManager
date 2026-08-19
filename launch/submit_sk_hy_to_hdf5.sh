#!/bin/bash
# Submit Super-K .hy -> chunked GhostHunter HDF5 (SLURM array) + optional concat.
#
# Env overrides:
#   DATA_DIR, INPUT_HY, INDICES_NPZ, INDICES_KEY
#   EVENTS_PER_CHUNK (default 5000), N_INDICES (required if using INDICES_NPZ)
#   CHUNK_DIR, OUTPUT_H5_STEM, FINAL_H5
#   EXTRA_ARGS (default: --min-hit-charge 0.11 --max-hit-charge none)
#   SKIP_CONCAT=1, STAGE_HY_TO_TMP=1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${DATA_DIR:?DATA_DIR required}"
LOG_DIR="${DATA_DIR}/logs"
CHUNK_DIR="${CHUNK_DIR:-${DATA_DIR}/h5/chunks_0.11_pe}"
mkdir -p "${LOG_DIR}" "${CHUNK_DIR}" "${DATA_DIR}/h5"

INPUT_HY="${INPUT_HY:?INPUT_HY required}"
OUTPUT_H5_STEM="${OUTPUT_H5_STEM:?OUTPUT_H5_STEM required}"
FINAL_H5="${FINAL_H5:?FINAL_H5 required}"

EVENTS_PER_CHUNK="${EVENTS_PER_CHUNK:-5000}"
N_INDICES="${N_INDICES:?N_INDICES required}"
N_CHUNKS=$(( (N_INDICES + EVENTS_PER_CHUNK - 1) / EVENTS_PER_CHUNK ))
ARRAY_MAX=$(( N_CHUNKS - 1 ))

export INPUT_HY OUTPUT_H5_STEM EVENTS_PER_CHUNK FINAL_H5 CHUNK_DIR
export INDICES_NPZ="${INDICES_NPZ:-}"
export INDICES_KEY="${INDICES_KEY:-event_idx}"
export STAGE_HY_TO_TMP="${STAGE_HY_TO_TMP:-1}"
export EXTRA_ARGS="${EXTRA_ARGS:---min-hit-charge 0.11 --max-hit-charge none}"

echo "Submitting sk_hy_to_h5 array: 0-${ARRAY_MAX} (${N_CHUNKS} chunks x ${EVENTS_PER_CHUNK} indices)"
echo "  DATA_DIR:   ${DATA_DIR}"
echo "  input:      ${INPUT_HY}"
echo "  indices:    ${INDICES_NPZ:-<none>}"
echo "  chunks dir: ${CHUNK_DIR}"
echo "  final h5:   ${FINAL_H5}"
echo "  EXTRA_ARGS: ${EXTRA_ARGS}"
echo "  stage .hy:  ${STAGE_HY_TO_TMP}"

ARRAY_JOB=$(sbatch \
    --array="0-${ARRAY_MAX}" \
    --output="${LOG_DIR}/sk_hy_to_h5_%A_%a.out" \
    --error="${LOG_DIR}/sk_hy_to_h5_%A_%a.err" \
    "${SCRIPT_DIR}/sk_hy_to_h5_slurm.sh" \
    | awk '{print $NF}')

echo "Submitted array job ${ARRAY_JOB}"

if [ "${SKIP_CONCAT:-0}" = "1" ]; then
    echo "SKIP_CONCAT=1 — merge later:"
    echo "  DATA_DIR=${DATA_DIR} CHUNK_GLOB=... OUTPUT_H5=... ${SCRIPT_DIR}/submit_sk_hy_concat.sh ${ARRAY_JOB}"
    exit 0
fi

export CHUNK_GLOB="${OUTPUT_H5_STEM}_chunk_*.h5"
export OUTPUT_H5="${FINAL_H5}"
export DATA_DIR LOG_DIR
CONCAT_JOB=$("${SCRIPT_DIR}/submit_sk_hy_concat.sh" "${ARRAY_JOB}" | awk '/Submitted concat job/{print $NF}')

echo "Submitted concat job ${CONCAT_JOB} (afterok:${ARRAY_JOB})"
