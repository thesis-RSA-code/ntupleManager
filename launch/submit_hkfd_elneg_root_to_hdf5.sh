#!/bin/bash
# Submit HK elneg production ntuple -> hierarchical HDF5 (~496k events).
set -euo pipefail

NTUPLEMANAGER_DIR="/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager"
YAML_CONFIG="/sps/t2k/eleblevec/mini-Caverns-toolsbox/datasets/hkfd_prod_elneg/hkfd_e-_rwcs_500k.yaml"
LOG_DIR="/sps/t2k/eleblevec/mini-Caverns-toolsbox/datasets/hkfd_prod_elneg/logs"
mkdir -p "${LOG_DIR}" "$(dirname "$(grep '^output_file:' "${YAML_CONFIG}" | sed 's/output_file: "//;s/"//')")"

SLURM_TIME="0-04:00:00"
SLURM_MEM="8G"
SLURM_PARTITION="htc"
ACCOUNT="t2k"
JOB_NAME="hkfd_elneg_hdf5_500k"

MINICONDA_DIR="/sps/t2k/eleblevec/miniconda3"
JOBS_DIR="/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager/jobs"
USE_TMP="true"

CONFIG_BASENAME=$(basename "${YAML_CONFIG}" .yaml)
TIMESTAMP=$(date +"%Y%m%d_%H_%M_%S")
JOB_DIR="${JOBS_DIR}/${TIMESTAMP}_root_to_h5_${CONFIG_BASENAME}"
mkdir -p "${JOB_DIR}"
SED_YAML_FILE="${JOB_DIR}/data_config.yaml"
cp "${YAML_CONFIG}" "${SED_YAML_FILE}"

echo "Job directory: ${JOB_DIR}"

sbatch \
    --time="${SLURM_TIME}" \
    --cpus-per-task=1 \
    --mem="${SLURM_MEM}" \
    --account="${ACCOUNT}" \
    --partition="${SLURM_PARTITION}" \
    --job-name="${JOB_NAME}" \
    --output="${LOG_DIR}/slurm_%x_%j.out" \
    --error="${LOG_DIR}/slurm_%x_%j.err" \
    --export=ALL,MINICONDA_DIR="${MINICONDA_DIR}",JOBS_DIR="${JOBS_DIR}",NTUPLEMANAGER_DIR="${NTUPLEMANAGER_DIR}",JOB_DIR="${JOB_DIR}",USE_TMP="${USE_TMP}" \
    "${NTUPLEMANAGER_DIR}/launch/root_to_hdf5_slurm.sh" \
    "${SED_YAML_FILE}"
