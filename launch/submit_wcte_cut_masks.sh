#!/bin/bash
# Submit WCTE cut-mask NPZ build (smoke 1k by default).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR=${LOG_DIR:-"/sps/t2k/eleblevec/Datasets/prod_datasets/wcte_check_plots/logs"}
mkdir -p "${LOG_DIR}"

JOB_ID=$(sbatch --parsable \
  --account=t2k \
  --partition=htc \
  --job-name=wcte_masks \
  --time=00:30:00 \
  --mem=4G \
  --cpus-per-task=1 \
  --output="${LOG_DIR}/wcte_cut_masks_%j.out" \
  --error="${LOG_DIR}/wcte_cut_masks_%j.err" \
  "${SCRIPT_DIR}/wcte_cut_masks_slurm.sh")

echo "Submitted wcte cut masks job: ${JOB_ID}"
echo "Logs: ${LOG_DIR}/wcte_cut_masks_${JOB_ID}.{out,err}"
