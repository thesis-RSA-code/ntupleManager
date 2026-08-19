#!/bin/bash
#SBATCH --account=t2k
#SBATCH --partition=htc
#SBATCH --job-name=sk_hy_to_h5_concat
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --time=12:00:00
#SBATCH --mem=32G

# Merge chunked hierarchical HDF5 files into one output (h5py copy, low RAM).
# Chunks are copied to /tmp one at a time before read; merged output also on /tmp.

set -euo pipefail

export PYTHONUNBUFFERED=1

MINICONDA_DIR=${MINICONDA_DIR:-"/sps/t2k/eleblevec/miniconda3"}
NTUPLEMANAGER_DIR=${NTUPLEMANAGER_DIR:-"/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager"}
CONDA_ENV=${CONDA_ENV:-"pt28_cuda129"}
PYTHON="${MINICONDA_DIR}/envs/${CONDA_ENV}/bin/python"
CONCAT_SCRIPT="${NTUPLEMANAGER_DIR}/utils/concat_hier_hdf5_chunks.py"

CHUNK_GLOB="${CHUNK_GLOB:?CHUNK_GLOB required}"
OUTPUT_H5="${OUTPUT_H5:?OUTPUT_H5 required}"

OUTPUT_DIR=$(dirname "$OUTPUT_H5")
OUTPUT_BASENAME=$(basename "$OUTPUT_H5" .h5)
JOB_TAG="${SLURM_JOB_ID:-local}"
TMP_H5="/tmp/${OUTPUT_BASENAME}_concat_${JOB_TAG}.h5"
TMP_STAGE="/tmp/sk_hy_chunks_${JOB_TAG}"

echo "Chunk glob: $CHUNK_GLOB"
echo "Stage dir:  $TMP_STAGE (one chunk at a time)"
echo "Temp out:   $TMP_H5"
echo "Final out:  $OUTPUT_H5"

# shellcheck source=/dev/null
source "${MINICONDA_DIR}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"

mkdir -p "$TMP_STAGE"

time "${PYTHON}" "${CONCAT_SCRIPT}" \
    --glob "$CHUNK_GLOB" \
    --output "$TMP_H5" \
    --stage-dir "$TMP_STAGE" \
    --progress-every 50000

rm -rf "$TMP_STAGE"

mkdir -p "$OUTPUT_DIR"
time mv -f "$TMP_H5" "$OUTPUT_H5"
echo "Done: $OUTPUT_H5"
