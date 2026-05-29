#!/bin/bash
# Submit WCTE ntuple -> hierarchical HDF5 production job (~1M events).
set -euo pipefail

NTUPLEMANAGER_DIR="/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager"
LOG_DIR="/sps/t2k/eleblevec/mini-Caverns-toolsbox/datasets/wcte_prod/logs"
mkdir -p "${LOG_DIR}"

SLURM_TIME="0-06:00:00"
SLURM_MEM="8G"
SLURM_PARTITION="htc"
ACCOUNT="t2k"
JOB_NAME="wcte_hdf5_1M"

INPUT_FILE="/sps/hyperk/mferey/Data/WCTE_v2/Concatenated/WCTE_uni_iso_FC_e-_0-1000MeV_3M_extra_data.root"
OUTPUT_FILE="/sps/t2k/eleblevec/mini-Caverns-toolsbox/datasets/wcte_prod/h5/WCTE_uni_iso_FC_e-_0-1000MeV.h5"

sbatch \
    --time="${SLURM_TIME}" \
    --cpus-per-task=1 \
    --mem="${SLURM_MEM}" \
    --account="${ACCOUNT}" \
    --partition="${SLURM_PARTITION}" \
    --job-name="${JOB_NAME}" \
    --output="${LOG_DIR}/slurm_%x_%j.out" \
    --error="${LOG_DIR}/slurm_%x_%j.err" \
    --export=ALL,MINICONDA_DIR="/sps/t2k/eleblevec/miniconda3",NTUPLEMANAGER_DIR="${NTUPLEMANAGER_DIR}",INPUT_FILE="${INPUT_FILE}",OUTPUT_FILE="${OUTPUT_FILE}" \
    "${NTUPLEMANAGER_DIR}/launch/wcte_root_to_hdf5_slurm.sh"
