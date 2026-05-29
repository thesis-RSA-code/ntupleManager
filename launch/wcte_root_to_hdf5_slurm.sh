#!/bin/bash
# SLURM worker: WCTE concatenated ROOT -> hierarchical HDF5 (~1M events).
# Submitted via submit_wcte_root_to_hdf5.sh

set -euo pipefail

MINICONDA_DIR=${MINICONDA_DIR:-"/sps/t2k/eleblevec/miniconda3"}
CONDA_ENV=${CONDA_ENV:-"pt28_cuda129"}
NTUPLEMANAGER_DIR=${NTUPLEMANAGER_DIR:-"/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager"}
INPUT_FILE=${INPUT_FILE:-"/sps/hyperk/mferey/Data/WCTE_v2/Concatenated/WCTE_uni_iso_FC_e-_0-1000MeV_3M_extra_data.root"}
OUTPUT_FILE=${OUTPUT_FILE:-"/sps/t2k/eleblevec/mini-Caverns-toolsbox/datasets/wcte_prod/h5/WCTE_uni_iso_FC_e-_0-1000MeV.h5"}
TREE_NAME=${TREE_NAME:-"pure_root_tree"}
STEP_SIZE=${STEP_SIZE:-"200MB"}

PYTHON="${MINICONDA_DIR}/envs/${CONDA_ENV}/bin/python"

TMPDIR=${TMPDIR:-/tmp}
TMP_H5="${TMPDIR}/wcte_prod_${SLURM_JOB_ID:-local}.h5"

echo "[wcte_hdf5] host=$(hostname) job=${SLURM_JOB_ID:-local} started $(date)"
echo "[wcte_hdf5] input=${INPUT_FILE}"
echo "[wcte_hdf5] output=${OUTPUT_FILE}"
echo "[wcte_hdf5] tmp_h5=${TMP_H5}"

# shellcheck source=/dev/null
source "${MINICONDA_DIR}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"

if [[ ! -x "${PYTHON}" ]]; then
    echo "[wcte_hdf5] ERROR: python not found at ${PYTHON}" >&2
    exit 1
fi
"${PYTHON}" -c "import h5py; print('[wcte_hdf5] h5py', h5py.__version__)"

cd "${NTUPLEMANAGER_DIR}"

"${PYTHON}" "${NTUPLEMANAGER_DIR}/root_to_hier_hdf5_wcte.py" \
    --detector WCTE \
    --input "${INPUT_FILE}" \
    --output "${TMP_H5}" \
    --tree-name "${TREE_NAME}" \
    --step-size "${STEP_SIZE}"

mkdir -p "$(dirname "${OUTPUT_FILE}")"
echo "[wcte_hdf5] copying HDF5 to final destination..."
time cp "${TMP_H5}" "${OUTPUT_FILE}"
rm -f "${TMP_H5}"

echo "[wcte_hdf5] finished $(date)"
