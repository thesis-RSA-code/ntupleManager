#!/bin/bash
# SLURM worker: extract train_val split from full WCTE HDF5 using NPZ indices.
# Uses node-local /tmp for read/write, then moves result to SPS.
# Submitted via submit_wcte_extract_train_val.sh

set -euo pipefail

MINICONDA_DIR=${MINICONDA_DIR:-"/sps/t2k/eleblevec/miniconda3"}
CONDA_ENV=${CONDA_ENV:-"pt28_cuda129"}
NTUPLEMANAGER_DIR=${NTUPLEMANAGER_DIR:-"/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager"}
H5_DIR=${H5_DIR:-"/sps/t2k/eleblevec/Datasets/prod_datasets/wcte_prod/h5"}

INPUT_SPS=${INPUT_SPS:-"${H5_DIR}/WCTE_uni_iso_FC_e-_0-1000MeV_TRAIN_VAL_TEST.h5"}
INDICES=${INDICES:-"${H5_DIR}/indices/wcte_e-_75_10_15_seed0.npz"}
OUTPUT_SPS=${OUTPUT_SPS:-"${H5_DIR}/WCTE_uni_iso_FC_e-_0-1000MeV_TRAIN_VAL.h5"}

JOB_TAG="${SLURM_JOB_ID:-local}"
TMP_IN="/tmp/wcte_src_${JOB_TAG}.h5"
TMP_OUT="/tmp/wcte_train_val_${JOB_TAG}.h5"

cleanup() {
    rm -f "${TMP_IN}" "${TMP_OUT}"
}
trap cleanup EXIT

PYTHON="${MINICONDA_DIR}/envs/${CONDA_ENV}/bin/python"
EXTRACT="${NTUPLEMANAGER_DIR}/utils/extract_hdf5_split.py"

echo "[wcte_extract_tv] host=$(hostname) job=${JOB_TAG} started $(date)"
echo "[wcte_extract_tv] input_sps=${INPUT_SPS}"
echo "[wcte_extract_tv] indices=${INDICES}"
echo "[wcte_extract_tv] output_sps=${OUTPUT_SPS}"
echo "[wcte_extract_tv] tmp_in=${TMP_IN} tmp_out=${TMP_OUT}"

# shellcheck source=/dev/null
source "${MINICONDA_DIR}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"

if [[ ! -f "${INPUT_SPS}" ]]; then
    echo "[wcte_extract_tv] ERROR: missing input ${INPUT_SPS}" >&2
    exit 1
fi
if [[ ! -f "${INDICES}" ]]; then
    echo "[wcte_extract_tv] ERROR: missing indices ${INDICES}" >&2
    exit 1
fi

echo "[wcte_extract_tv] copying source HDF5 to /tmp..."
time cp -a "${INPUT_SPS}" "${TMP_IN}"

echo "[wcte_extract_tv] extracting train_val split..."
time "${PYTHON}" "${EXTRACT}" \
    --input "${TMP_IN}" \
    --indices "${INDICES}" \
    --split train_val \
    --output "${TMP_OUT}"

echo "[wcte_extract_tv] moving output to ${OUTPUT_SPS}..."
mkdir -p "$(dirname "${OUTPUT_SPS}")"
time mv "${TMP_OUT}" "${OUTPUT_SPS}"
# TMP_OUT gone; disable trap removal of it (already moved)
trap 'rm -f "${TMP_IN}"' EXIT
rm -f "${TMP_IN}"

echo "[wcte_extract_tv] finished $(date)"
ls -lh "${OUTPUT_SPS}"
