#!/bin/bash
# Submit WCTE TRAIN_VAL HDF5 split extraction (~879k events, ~26GB output).
set -euo pipefail

NTUPLEMANAGER_DIR="/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager"
H5_DIR="/sps/t2k/eleblevec/Datasets/prod_datasets/wcte_prod/h5"
LOG_DIR="${H5_DIR}/logs"
mkdir -p "${LOG_DIR}"

SLURM_TIME="0-08:00:00"
SLURM_MEM="16G"
SLURM_PARTITION="htc"
ACCOUNT="t2k"
JOB_NAME="wcte_extract_tv"

INPUT_SPS="${H5_DIR}/WCTE_uni_iso_FC_e-_0-1000MeV_TRAIN_VAL_TEST.h5"
INDICES="${H5_DIR}/indices/wcte_e-_75_10_15_seed0.npz"
OUTPUT_SPS="${H5_DIR}/WCTE_uni_iso_FC_e-_0-1000MeV_TRAIN_VAL.h5"

sbatch \
    --time="${SLURM_TIME}" \
    --cpus-per-task=1 \
    --mem="${SLURM_MEM}" \
    --account="${ACCOUNT}" \
    --partition="${SLURM_PARTITION}" \
    --job-name="${JOB_NAME}" \
    --output="${LOG_DIR}/slurm_%x_%j.out" \
    --error="${LOG_DIR}/slurm_%x_%j.err" \
    --export=ALL,MINICONDA_DIR="/sps/t2k/eleblevec/miniconda3",NTUPLEMANAGER_DIR="${NTUPLEMANAGER_DIR}",H5_DIR="${H5_DIR}",INPUT_SPS="${INPUT_SPS}",INDICES="${INDICES}",OUTPUT_SPS="${OUTPUT_SPS}" \
    "${NTUPLEMANAGER_DIR}/launch/wcte_extract_train_val_slurm.sh"
