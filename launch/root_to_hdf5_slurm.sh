#!/bin/bash

## SBATCH --account=hyperk
#SBATCH --account=t2k
#SBATCH --partition=htc
#SBATCH --job-name=t2k_root_to_h5
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --time=0-01:00:00
#SBATCH --mem=20G

# SLURM wrapper for root_to_hier_hdf5.py
# Usage: sbatch root_to_hdf5_slurm.sh <yaml_config_file>

MINICONDA_DIR=${MINICONDA_DIR:-"/sps/t2k/eleblevec/miniconda3"}
JOBS_DIR=${JOBS_DIR:-"/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager/jobs"}
NTUPLEMANAGER_DIR=${NTUPLEMANAGER_DIR:-"/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager"}
JOB_DIR=${JOB_DIR:-""}
ROOT_TO_HDF5_SCRIPT_NAME="root_to_hier_hdf5"

USE_TMP=${USE_TMP:-"false"} # whether to copy the root file into /tmp; hdf5 is always written in TMPDIR first

## --- overwrite exported variables if needed --- ##
TMPDIR=/tmp
USE_TMP="true"

## EXECUTED CODE ##
yaml_file=$1
tmp_file=""

# Check if yaml file is provided
if [ -z "$yaml_file" ]; then
    echo "Error: Please provide a yaml config file as argument"
    echo "Usage: sbatch root_to_hdf5_slurm.sh <yaml_config_file>"
    exit 1
fi

# Check if yaml file exists
if [ ! -f "$yaml_file" ]; then
    echo "Error: YAML file '$yaml_file' not found"
    exit 1
fi

# Check if input_file exists in yaml (only uncommented lines)
if ! grep -q "^input_file:" $yaml_file; then
    echo "Error: input_file not found in $yaml_file"
    exit 1
fi

# Use job directory passed from submit script, or create one if not provided
if [ -n "$JOB_DIR" ]; then
    echo "Using provided job directory: $JOB_DIR"
else
    echo "No job directory provided, creating one..."

    CONFIG_BASENAME=$(basename "$yaml_file" .yaml)
    TIMESTAMP=$(date +"%Y%m%d_%H_%M_%S")
    JOB_FOLDER="${TIMESTAMP}_root_to_h5_${CONFIG_BASENAME}"
    JOB_DIR="$JOBS_DIR/$JOB_FOLDER"
    mkdir -p "$JOB_DIR"
    echo "Created job directory: $JOB_DIR"

    echo "Making a copy of the yaml file in the job directory: $JOB_DIR"
    cp $yaml_file $JOB_DIR/data_config.yaml
    yaml_file=$JOB_DIR/data_config.yaml
fi

# Extract filenames from the original paths in config (only uncommented lines)
ROOT_FILE_PATH=$(grep "^input_file:" $yaml_file | sed 's/input_file: "//' | sed 's/"//')
ROOT_FILENAME=$(basename "$ROOT_FILE_PATH")

H5_FILE_PATH=$(grep "^output_file:" $yaml_file | sed 's/output_file: "//' | sed 's/"//')
H5_FILENAME=$(basename "$H5_FILE_PATH")

# Determine where to read the ROOT file from
if [ "$USE_TMP" = "true" ]; then
    CURRENT_TIME=$(date +%s%3N)
    TMP_ROOT_FILE="$TMPDIR/${ROOT_FILENAME%.root}_${CURRENT_TIME}_${SLURM_JOB_ID}.root"
    echo "Copying ROOT file to local temp space: $TMP_ROOT_FILE"
    time cp "$ROOT_FILE_PATH" "$TMP_ROOT_FILE"
else
    TMP_ROOT_FILE="$ROOT_FILE_PATH"
    echo "Reading ROOT file directly from source (No copy to TMP): $ROOT_FILE_PATH"
fi
TMP_H5_FILE="${TMPDIR}/${H5_FILENAME%.h5}_${CURRENT_TIME}_${SLURM_JOB_ID}.h5"

# Point config at temp paths for this run
sed -i "s|^input_file: \".*\"|input_file: \"$TMP_ROOT_FILE\"|" $yaml_file
sed -i "s|^output_file: \".*\"|output_file: \"$TMP_H5_FILE\"|" $yaml_file

echo "Starting ROOT to HDF5 conversion..."
echo "Working directory: $(pwd)"
echo "Python script: $NTUPLEMANAGER_DIR/${ROOT_TO_HDF5_SCRIPT_NAME}.py"
echo "Config file: $yaml_file"

CONDA_ENV=${CONDA_ENV:-"pt28_cuda129"}
PYTHON="${MINICONDA_DIR}/envs/${CONDA_ENV}/bin/python"
# shellcheck source=/dev/null
source "${MINICONDA_DIR}/etc/profile.d/conda.sh"
conda activate "${CONDA_ENV}"
"${PYTHON}" -c 'import h5py; print("h5py", h5py.__version__)'
"${PYTHON}" $NTUPLEMANAGER_DIR/${ROOT_TO_HDF5_SCRIPT_NAME}.py --config $yaml_file

if [ $? -eq 0 ]; then
    echo "ROOT to HDF5 conversion completed successfully"

    H5_FOLDER_PATH=$(dirname "$H5_FILE_PATH")
    echo "Copying H5 file back to: $H5_FILE_PATH"
    mkdir -p "$H5_FOLDER_PATH"
    time cp "$TMP_H5_FILE" "$H5_FILE_PATH"

    if [ "$USE_TMP" = "true" ] && [ -f "$TMP_ROOT_FILE" ]; then
        echo "Cleaning up temporary ROOT file: $TMP_ROOT_FILE"
        rm -f "$TMP_ROOT_FILE"
    fi
    rm -f "$TMP_H5_FILE"
    echo "Temporary files cleaned up, job directory preserved: $JOB_DIR"
else
    echo "**********************************************************************"
    echo "* Error: ROOT to HDF5 conversion failed                             *"
    echo "* Job directory with intermediate files preserved: $JOB_DIR"
    echo "**********************************************************************"
    exit 1
fi
