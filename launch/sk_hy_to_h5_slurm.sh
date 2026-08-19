#!/bin/bash
#SBATCH --account=t2k
#SBATCH --partition=htc
#SBATCH --job-name=sk_hy_to_h5
#SBATCH --output=%x_%A_%a.out
#SBATCH --error=%x_%A_%a.err
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --time=02:00:00
#SBATCH --mem=32G

# SLURM array worker: WatChMaL .hy slice -> hierarchical HDF5 chunk.
#
# Required env:
#   INPUT_HY, OUTPUT_H5_STEM, EVENTS_PER_CHUNK
# Optional:
#   INDICES_NPZ, INDICES_KEY (default event_idx)
#   EXTRA_ARGS, STAGE_HY_TO_TMP (default 1)
#
# Stages the .hy on /tmp once per array job (shared path via flock), writes chunk on
# /tmp, then mv to CHUNK_DIR on /sps.

set -euo pipefail

export PYTHONUNBUFFERED=1

: "${INPUT_HY:?INPUT_HY required}"
: "${OUTPUT_H5_STEM:?OUTPUT_H5_STEM required}"
: "${EVENTS_PER_CHUNK:?EVENTS_PER_CHUNK required}"

CHUNK_INDEX="${SLURM_ARRAY_TASK_ID:-0}"
STAGE_HY_TO_TMP="${STAGE_HY_TO_TMP:-1}"

MINICONDA_DIR=${MINICONDA_DIR:-"/sps/t2k/eleblevec/miniconda3"}
NTUPLEMANAGER_DIR=${NTUPLEMANAGER_DIR:-"/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager"}
CONDA_ENV=${CONDA_ENV:-"pt28_cuda129"}
PYTHON="${MINICONDA_DIR}/envs/${CONDA_ENV}/bin/python"
HY_SCRIPT="${NTUPLEMANAGER_DIR}/hy_flat_to_hier_hdf5.py"

INPUT_HY_ORIG="$INPUT_HY"
if [[ "$STAGE_HY_TO_TMP" == "1" ]]; then
    HY_BASENAME=$(basename "$INPUT_HY")
    TMP_HY="/tmp/${HY_BASENAME%.hy}_arr${SLURM_ARRAY_JOB_ID:-local}.hy"
    STAGE_LOCK="/tmp/stage_${HY_BASENAME%.hy}_arr${SLURM_ARRAY_JOB_ID:-local}.lock"
    (
        flock -x 9
        if [[ ! -f "$TMP_HY" ]]; then
            echo "[hy] staging ${INPUT_HY_ORIG} -> ${TMP_HY}"
            rsync -a --partial "${INPUT_HY_ORIG}" "${TMP_HY}"
        else
            echo "[hy] reusing staged ${TMP_HY}"
        fi
    ) 9>"${STAGE_LOCK}"
    INPUT_HY="$TMP_HY"
fi

OUTPUT_DIR=$(dirname "$OUTPUT_H5_STEM")
mkdir -p "$OUTPUT_DIR"
CHUNK_TAG=$(printf "%05d" "$CHUNK_INDEX")
FINAL_CHUNK="${OUTPUT_H5_STEM}_chunk_${CHUNK_TAG}.h5"
TMP_STEM="/tmp/$(basename "${OUTPUT_H5_STEM}")_${SLURM_ARRAY_JOB_ID:-arr}_${SLURM_JOB_ID:-local}"
TMP_CHUNK="${TMP_STEM}_chunk_${CHUNK_TAG}.h5"

echo "Array job: ${SLURM_ARRAY_JOB_ID:-?} task ${CHUNK_INDEX}"
echo "Input .hy: $INPUT_HY"
echo "Indices:   ${INDICES_NPZ:-<sequential --start/--stop>}"
echo "Events/chunk: $EVENTS_PER_CHUNK"
echo "Temp chunk: $TMP_CHUNK"
echo "Final chunk: $FINAL_CHUNK"
echo "Extra:     ${EXTRA_ARGS:-<none>}"

# shellcheck source=/dev/null
source "${MINICONDA_DIR}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"

INDICES_ARGS=()
if [[ -n "${INDICES_NPZ:-}" ]]; then
    INDICES_ARGS=(--indices-npz "$INDICES_NPZ" --indices-key "${INDICES_KEY:-event_idx}")
fi

# shellcheck disable=SC2086
time "${PYTHON}" "${HY_SCRIPT}" \
    --input "$INPUT_HY" \
    --output "${TMP_STEM}.h5" \
    "${INDICES_ARGS[@]}" \
    --chunk-index "$CHUNK_INDEX" \
    --events-per-chunk "$EVENTS_PER_CHUNK" \
    --chunk-size 500 \
    ${EXTRA_ARGS:---min-hit-charge 0.11 --max-hit-charge none}

echo "Moving chunk to final destination..."
time mv -f "$TMP_CHUNK" "$FINAL_CHUNK"
echo "Done: $FINAL_CHUNK"
