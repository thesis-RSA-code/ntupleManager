#!/bin/bash
# SLURM worker: build event-cut masks NPZ from hierarchical WCTE HDF5.

set -euo pipefail

MINICONDA_DIR=${MINICONDA_DIR:-"/sps/t2k/eleblevec/miniconda3"}
CONDA_ENV=${CONDA_ENV:-"pt28_cuda129"}
NTUPLEMANAGER_DIR=${NTUPLEMANAGER_DIR:-"/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager"}
CONFIG=${CONFIG:-"${NTUPLEMANAGER_DIR}/configs/wcte_nhits_gt80_smoke_1k.yaml"}

export PYTHONUNBUFFERED=1
PYTHON="${MINICONDA_DIR}/envs/${CONDA_ENV}/bin/python"

echo "[wcte_masks] host=$(hostname) job=${SLURM_JOB_ID:-local} started $(date)"
echo "[wcte_masks] config=${CONFIG}"

# shellcheck source=/dev/null
source "${MINICONDA_DIR}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"

cd "${NTUPLEMANAGER_DIR}"
"${PYTHON}" utils/build_hdf5_cut_masks.py --config "${CONFIG}" --progress-every 200

echo "[wcte_masks] done $(date)"
