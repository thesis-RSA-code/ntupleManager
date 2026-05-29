#!/bin/bash

# Wrapper script to submit root_to_hdf5 jobs with proper output directory structure
# Usage: ./submit_root_to_hdf5.sh <yaml_config_file>
#
# SLURM Configuration (edit these values as needed):
SLURM_TIME="1-00:00:00"      # Time limit
SLURM_MEM="30GB"              # Memory limit
JOB_NAME="HK_tv_1M_e-_root_to_h5"
ACCOUNT="t2k"

# Directory Configuration (edit these paths as needed):
# Will be exported to the job
MINICONDA_DIR="/sps/t2k/eleblevec/miniconda3"         
JOBS_DIR="/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager/jobs"  # Where job folders are created
NTUPLEMANAGER_DIR="/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager"  # Main project directory
ROOT_TO_HDF5_SCRIPT_NAME="root_to_hier_hdf5"
USE_TMP="true"

# Not exported variables
SLURM_PARTITION="htc"


# --------- EXECUTED CODE --------- #
yaml_file=$1

# Check if yaml file is provided
if [ -z "$yaml_file" ]; then
    echo "Error: Please provide a yaml config file as argument"
    echo "Usage: $0 <yaml_config_file>"
    echo ""
    echo "To modify SLURM resources and paths, edit the variables at the top of this script:"
    echo ""
    echo "SLURM Configuration:"
    echo "  SLURM_TIME=\"0-01:00:00\"    # Time limit"
    echo "  SLURM_MEM=\"20G\"            # Memory limit"
    echo ""
    echo "Directory Configuration:"
    echo "  MINICONDA_DIR=\"...\"        # Miniconda installation path"
    echo "  JOBS_DIR=\"...\"             # Where job folders are created"
    echo "  NTUPLEMANAGER_DIR=\"...\"    # Main project directory"
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

# Generate job folder name using timestamp and config filename
CONFIG_BASENAME=$(basename "$yaml_file" .yaml)
TIMESTAMP=$(date +"%Y%m%d_%H_%M_%S")
JOB_FOLDER="${TIMESTAMP}_root_to_h5_${CONFIG_BASENAME}"

# Create jobs directory and job-specific directory
JOB_DIR="$JOBS_DIR/$JOB_FOLDER"
mkdir -p "$JOB_DIR"

SED_YAML_FILE="$JOB_DIR/data_config.yaml"
cp $yaml_file $SED_YAML_FILE

echo "Job directory: $JOB_DIR"
echo "Job folder name: $JOB_FOLDER"
echo "SLURM resources: Time=$SLURM_TIME, Memory=$SLURM_MEM"
echo ""


# Submit the job with output files directed to the job directory
sbatch \
    --time="$SLURM_TIME" \
    --mem="$SLURM_MEM" \
    --account="$ACCOUNT" \
    --partition="$SLURM_PARTITION" \
    --output="$JOB_DIR/slurm_%x_%j.out" \
    --error="$JOB_DIR/slurm_%x_%j.err" \
    --job-name="$JOB_NAME" \
    --export=MINICONDA_DIR="$MINICONDA_DIR",JOBS_DIR="$JOBS_DIR",NTUPLEMANAGER_DIR="$NTUPLEMANAGER_DIR",JOB_DIR="$JOB_DIR",ROOT_TO_HDF5_SCRIPT_NAME="$ROOT_TO_HDF5_SCRIPT_NAME",GEOMETRY="$GEOMETRY",USE_TMP="$USE_TMP" \
    "$NTUPLEMANAGER_DIR/launch/root_to_hdf5_slurm.sh" \
    "$SED_YAML_FILE"

echo "Job submitted successfully!"
echo "SLURM output files will be in: $JOB_DIR"
