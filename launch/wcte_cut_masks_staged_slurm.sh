#!/bin/bash
# SLURM worker: stage hierarchical WCTE HDF5 on /tmp, then build cut-mask NPZ.

set -euo pipefail

MINICONDA_DIR=${MINICONDA_DIR:-"/sps/t2k/eleblevec/miniconda3"}
CONDA_ENV=${CONDA_ENV:-"pt28_cuda129"}
NTUPLEMANAGER_DIR=${NTUPLEMANAGER_DIR:-"/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager"}
CONFIG=${CONFIG:?CONFIG required}
HDF5_SPS=${HDF5_SPS:?HDF5_SPS required}

JOB_TAG="${SLURM_JOB_ID:-local}"
TMP_H5="/tmp/wcte_masks_src_${JOB_TAG}.h5"

cleanup() {
    rm -f "${TMP_H5}"
}
trap cleanup EXIT

export PYTHONUNBUFFERED=1
PYTHON="${MINICONDA_DIR}/envs/${CONDA_ENV}/bin/python"

echo "[wcte_masks_staged] host=$(hostname) job=${JOB_TAG} started $(date)"
echo "[wcte_masks_staged] config=${CONFIG}"
echo "[wcte_masks_staged] hdf5_sps=${HDF5_SPS}"
echo "[wcte_masks_staged] tmp_h5=${TMP_H5}"

# shellcheck source=/dev/null
source "${MINICONDA_DIR}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"

if [[ ! -f "${HDF5_SPS}" ]]; then
    echo "[wcte_masks_staged] ERROR: missing ${HDF5_SPS}" >&2
    exit 1
fi

echo "[wcte_masks_staged] copying HDF5 to /tmp..."
time cp -a "${HDF5_SPS}" "${TMP_H5}"

cd "${NTUPLEMANAGER_DIR}"
echo "[wcte_masks_staged] building masks from staged file..."
time "${PYTHON}" utils/build_hdf5_cut_masks.py \
    --config "${CONFIG}" \
    --hdf5 "${TMP_H5}" \
    --progress-every 100000

echo "[wcte_masks_staged] done $(date)"
