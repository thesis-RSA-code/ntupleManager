#!/bin/bash

module load Analysis/root/6.30.06

# Source hierarchical hadd library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/hadd_hierarchical_lib.sh"

###############
# Processing Options
###############
# Choose what to process: "both", "test", "train_val"
PROCESS_MODE="test"

# Use scratch directory for faster processing (copies files to $TMP_DIR before hadd)
# Set to "true" to enable, "false" to disable
USE_SCRATCH_DIR="true"

# Scratch directory (typically local fast storage on compute node)
TMP_DIR="${TMPDIR:-/tmp/hadd_wcte_scratch_$$}"

# Hierarchical merging configuration
# Number of hierarchy levels (1 = simple merge all at once, 2+ = hierarchical)
# For large datasets (1000+ files), recommend 2-3 levels to avoid file descriptor limits
HIERARCHY_LEVELS=2

# Verbose copy mode - show progress during file copying to scratch
# Set to "true" to enable progress display, "false" for quiet mode
VERBOSE_COPY="true"

###############
# Dataset Configuration
###############
PARTICLE="e-"

# --WCTE dataset
ENERGY_RANGE="200-1000MeV"
BASEFILE_NAME="ntuple_cut_ed_2000.root"

# BASE_INPUT_DIR=/sps/t2k/mferey/Data/WCTE_v1/WCTE_center_iso/WCSim_v1.12.20_nuPRISMBeamTest_16cShort_mPMT
BASE_INPUT_DIR=/sps/t2k/eleblevec/Datasets/custom_dataset/e-/200-1000MeV/WCTE_center_iso_erwan_cuts
FINAL_INPUT_DIR=${BASE_INPUT_DIR}
# FINAL_INPUT_DIR=${BASE_INPUT_DIR}

TEST_STARTFILE=1
TEST_END_FILE=50
TRAIN_VAL_STARTFILE=51
TRAIN_VAL_END_FILE=500


BASE_SAVE_DIR="/sps/t2k/eleblevec/Datasets/custom_dataset/${PARTICLE}/${ENERGY_RANGE}/WCTE_center_iso_1Mevents"
mkdir -p $BASE_SAVE_DIR

# OUTFILE_NAME="merged_root_output_${PARTICLE}_${ENERGY_RANGE}_folder${STARTFILE}_a$((STARTFILE + NFILES - 1)).root"
# OUTFILE_NAME="merged_fq_output_${PARTICLE}_${ENERGY_RANGE}_folder${STARTFILE}_a$((STARTFILE + NFILES - 1)).root"

###############
# Validation
###############
if [[ "$PROCESS_MODE" != "both" && "$PROCESS_MODE" != "test" && "$PROCESS_MODE" != "train_val" ]]; then
    echo "ERROR: PROCESS_MODE must be 'both', 'test', or 'train_val'"
    exit 1
fi

if ! validate_hierarchy_config "$HIERARCHY_LEVELS"; then
    exit 1
fi

echo "=========================================="
echo "Processing mode: $PROCESS_MODE"
echo "Hierarchy levels: $HIERARCHY_LEVELS"
echo "Use scratch directory: $USE_SCRATCH_DIR"
if [ "$USE_SCRATCH_DIR" = "true" ]; then
    echo "Scratch directory: $TMP_DIR"
    echo "Verbose copy: $VERBOSE_COPY"
fi
echo "=========================================="
echo ""

###############
# Make test set
###############
if [[ "$PROCESS_MODE" == "both" || "$PROCESS_MODE" == "test" ]]; then
echo ""
echo "=========================================="
echo "Processing TEST set"
echo "=========================================="
mkdir -p $BASE_SAVE_DIR/test_${TEST_STARTFILE}_a${TEST_END_FILE}
OUTFILE_NAME=merged_${PARTICLE}_${ENERGY_RANGE}.root

echo ""
echo -e "Input PARTICLE example : \n${FINAL_INPUT_DIR}/${TEST_STARTFILE}/ \nChecking with ls..\n"
ls -l ${FINAL_INPUT_DIR}/${TEST_STARTFILE}/${BASEFILE_NAME}
echo ""
echo -e "Will save test set as : \n${BASE_SAVE_DIR}/test_${TEST_STARTFILE}_a${TEST_END_FILE}/${OUTFILE_NAME}"

LIST=""
lost_files=0
for i in $(seq $TEST_STARTFILE $TEST_END_FILE); do
    FILE=${FINAL_INPUT_DIR}/${i}/${BASEFILE_NAME}
    # echo $i
    # echo $FILE

    if [ -f $FILE ]; then
	    LIST="${LIST} ${FILE}"
    else
	    echo "File does not exist: $i"
        lost_files=$((lost_files + 1))
    fi
done
echo "Processed up to folder: $i"
echo "[TEST] Lost files: $lost_files"
echo "[TEST] Found files: $((TEST_END_FILE - TEST_STARTFILE + 1 - lost_files))"
# exit 0

hadd_hierarchical_merge \
    "${BASE_SAVE_DIR}/test_${TEST_STARTFILE}_a${TEST_END_FILE}/${OUTFILE_NAME}" \
    "${BASE_SAVE_DIR}/test_${TEST_STARTFILE}_a${TEST_END_FILE}/hadd_${PARTICLE}_${ENERGY_RANGE}_MeV_folder${TEST_STARTFILE}_a${TEST_END_FILE}.log" \
    "$LIST" \
    "TEST" \
    "$HIERARCHY_LEVELS" \
    "$USE_SCRATCH_DIR" \
    "${TMP_DIR}_test" \
    "$VERBOSE_COPY"

echo "Saved file: ${BASE_SAVE_DIR}/test_${TEST_STARTFILE}_a${TEST_END_FILE}/${OUTFILE_NAME}"
echo ""
fi


###############
# Make train_val set
###############
if [[ "$PROCESS_MODE" == "both" || "$PROCESS_MODE" == "train_val" ]]; then
echo ""
echo "=========================================="
echo "Processing TRAIN_VAL set"
echo "=========================================="
mkdir -p $BASE_SAVE_DIR/train_val_${TRAIN_VAL_STARTFILE}_a${TRAIN_VAL_END_FILE}
OUTFILE_NAME=merged_${PARTICLE}_${ENERGY_RANGE}.root



echo -e "Input PARTICLE example : \n${FINAL_INPUT_DIR}/n/ \nChecking with ls..\n"
ls -l ${FINAL_INPUT_DIR}/${TRAIN_VAL_STARTFILE}/${BASEFILE_NAME}
echo ""
echo -e "Will save train_val set as : \n${BASE_SAVE_DIR}/train_val_${TRAIN_VAL_STARTFILE}_a${TRAIN_VAL_END_FILE}/${OUTFILE_NAME}"
# exit 0

LIST=""
lost_files=0
for i in $(seq $TRAIN_VAL_STARTFILE $TRAIN_VAL_END_FILE); do
    FILE=${FINAL_INPUT_DIR}/${i}/${BASEFILE_NAME}
    # echo $i
    # echo $FILE
    if [ -f $FILE ]; then
        LIST="${LIST} ${FILE}"
    else
        echo "File does not exist: $i"
        lost_files=$((lost_files + 1))
    fi
done
echo "Processed up to folder: $i"
echo "[TRAIN_VAL] Lost files: $lost_files"
echo "[TRAIN_VAL] Found files: $((TRAIN_VAL_END_FILE - TRAIN_VAL_STARTFILE + 1 - lost_files))"

hadd_hierarchical_merge \
    "${BASE_SAVE_DIR}/train_val_${TRAIN_VAL_STARTFILE}_a${TRAIN_VAL_END_FILE}/${OUTFILE_NAME}" \
    "${BASE_SAVE_DIR}/train_val_${TRAIN_VAL_STARTFILE}_a${TRAIN_VAL_END_FILE}/hadd_${PARTICLE}_${ENERGY_RANGE}_MeV_folder${TRAIN_VAL_STARTFILE}_a${TRAIN_VAL_END_FILE}.log" \
    "$LIST" \
    "TRAIN_VAL" \
    "$HIERARCHY_LEVELS" \
    "$USE_SCRATCH_DIR" \
    "${TMP_DIR}_train_val" \
    "$VERBOSE_COPY"

echo "Saved file: ${BASE_SAVE_DIR}/train_val_${TRAIN_VAL_STARTFILE}_a${TRAIN_VAL_END_FILE}/${OUTFILE_NAME}"
echo ""
fi

echo "=========================================="
echo "All done!"
echo "=========================================="