#!/bin/bash

# Script to clean up dummy job folders in ntupleManager/jobs
# Deletes folders that:
#   1. Contain "dummy" in their name (regardless of contents), OR
#   2. Are empty or contain only .yaml config files (regardless of name)
#
# Real jobs will have .err and/or .out files from SLURM, so they are preserved
#
# Usage: ./clean_jobs.sh [--dry-run]
#   --dry-run: Show what would be deleted without actually deleting

JOBS_DIR=/sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager/jobs
DRY_RUN=false

if [ "$1" == "--dry-run" ]; then
    DRY_RUN=true
    echo "DRY RUN MODE - No files will be deleted"
    echo ""
fi


if [ ! -d "$JOBS_DIR" ]; then
    echo "Error: Jobs directory not found: $JOBS_DIR"
    exit 1
fi

echo "Cleaning dummy job folders in: $JOBS_DIR"
echo ""

deleted_count=0
checked_count=0

# Iterate through all folders in the jobs directory
for folder in "$JOBS_DIR"/*; do
    # Check if it's a directory
    if [ ! -d "$folder" ]; then
        continue
    fi
    
    folder_name=$(basename "$folder")
    ((checked_count++))
    
    should_delete=false
    delete_reason=""
    
    # Check if folder name contains "dummy"
    if [[ "$folder_name" == *"dummy"* ]]; then
        should_delete=true
        delete_reason="contains 'dummy' in name"
    fi
    
    # Check if folder is empty or contains only .yaml files
    files_in_folder=$(find "$folder" -type f 2>/dev/null)
    
    if [ -z "$files_in_folder" ]; then
        # Folder is empty
        should_delete=true
        delete_reason="empty"
    else
        # Check if all files are .yaml files
        non_yaml_files=$(find "$folder" -type f ! -name "*.yaml" ! -name "*.yml" 2>/dev/null)
        
        if [ -z "$non_yaml_files" ]; then
            # Only .yaml files present
            should_delete=true
            delete_reason="only .yaml files"
        fi
    fi
    
    # Delete if either condition is met
    if [ "$should_delete" = true ]; then
        if [ "$DRY_RUN" = true ]; then
            echo "Would delete folder ($delete_reason): $folder_name"
        else
            echo "Deleting folder ($delete_reason): $folder_name"
            rm -rf "$folder"
        fi
        ((deleted_count++))
    fi
done

echo ""
if [ "$DRY_RUN" = true ]; then
    echo "Dry run complete!"
    echo "  Checked: $checked_count folders"
    echo "  Would delete: $deleted_count folders"
    if [ $deleted_count -eq 0 ]; then
        echo "  No folders found to clean."
    fi
    echo ""
    echo "Run without --dry-run to actually delete these folders."
else
    echo "Cleanup complete!"
    echo "  Checked: $checked_count folders"
    echo "  Deleted: $deleted_count folders"
    if [ $deleted_count -eq 0 ]; then
        echo "  No folders found to clean."
    fi
fi

