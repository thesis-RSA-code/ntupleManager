#!/bin/bash

###############################################################################
# hadd_hierarchical_lib.sh
# 
# Reusable library for hierarchical ROOT file merging with hadd
# Supports multi-level merging to avoid hitting file descriptor limits
# and provides progress tracking for file copying operations.
#
# Usage:
#   source hadd_hierarchical_lib.sh
#   hadd_hierarchical_merge "$output_file" "$log_file" "$file_list" "$dataset_name" \
#                           "$hierarchy_levels" "$use_scratch" "$tmp_dir" "$verbose_copy"
###############################################################################

###############################################################################
# Function: display_copy_progress
# Displays progress during file copying operations
#
# Arguments:
#   $1 - current count
#   $2 - total count
#   $3 - dataset name
#   $4 - display interval (show every N files)
###############################################################################
function display_copy_progress() {
    local current=$1
    local total=$2
    local dataset_name=$3
    local interval=$4
    
    if [ $((current % interval)) -eq 0 ] || [ $current -eq $total ]; then
        local percent=$((current * 100 / total))
        echo "[$dataset_name] Copying files: $current/$total ($percent%)"
    fi
}

###############################################################################
# Function: calculate_batch_size
# Calculates optimal batch size for hierarchical merging
#
# Arguments:
#   $1 - total number of files
#   $2 - number of hierarchy levels
#
# Returns (echoes):
#   batch_size - files per batch for first level
###############################################################################
function calculate_batch_size() {
    local total_files=$1
    local levels=$2
    
    if [ $levels -le 0 ]; then
        echo "ERROR: hierarchy levels must be > 0" >&2
        echo "1"
        return 1
    fi
    
    if [ $levels -eq 1 ]; then
        # Single level: merge all files at once
        echo "$total_files"
        return 0
    fi
    
    # Calculate nth root to determine batch size
    # For N files and L levels, batch_size ≈ N^(1/L)
    # We'll use a practical approach with awk
    local batch_size=$(awk -v n="$total_files" -v l="$levels" 'BEGIN {
        result = exp(log(n) / l)
        # Round up to ensure we dont have too many batches
        print int(result + 0.999)
    }')
    
    # Minimum batch size of 2 (otherwise no point in hierarchical merge)
    if [ $batch_size -lt 2 ]; then
        batch_size=2
    fi
    
    echo "$batch_size"
}

###############################################################################
# Function: merge_batch_of_files
# Merges a batch of ROOT files using hadd
#
# Arguments:
#   $1 - output file path
#   $2 - log file path
#   $3 - space-separated list of input files
#   $4 - dataset name (for logging)
###############################################################################
function merge_batch_of_files() {
    local output_file=$1
    local log_file=$2
    local file_list=$3
    local dataset_name=$4
    
    local num_files=$(echo $file_list | wc -w)
    echo "[$dataset_name] Merging $num_files files -> $(basename $output_file)"
    
    hadd -f "$output_file" $file_list >> "$log_file" 2>&1
    
    if [ $? -ne 0 ]; then
        echo "" >&2
        echo "========================================" >&2
        echo "[$dataset_name] ERROR: hadd failed for $(basename $output_file)" >&2
        echo "========================================" >&2
        echo "Last 30 lines of log file:" >&2
        echo "----------------------------------------" >&2
        tail -n 30 "$log_file" >&2
        echo "----------------------------------------" >&2
        echo "Full log available at: $log_file" >&2
        echo "========================================" >&2
        echo "" >&2
        return 1
    fi
    
    return 0
}

###############################################################################
# Function: hadd_hierarchical_merge
# Main function for hierarchical ROOT file merging
#
# Arguments:
#   $1 - final output file path
#   $2 - log file path
#   $3 - space-separated list of input files
#   $4 - dataset name (for logging)
#   $5 - number of hierarchy levels (1 = simple merge, 2+ = hierarchical)
#   $6 - use scratch directory ("true" or "false")
#   $7 - scratch directory path
#   $8 - verbose copy mode ("true" or "false")
###############################################################################
function hadd_hierarchical_merge() {
    local final_output=$1
    local log_file=$2
    local input_list=$3
    local dataset_name=$4
    local hierarchy_levels=${5:-1}
    local use_scratch=${6:-false}
    local scratch_dir=${7:-/tmp/hadd_scratch_$$}
    local verbose_copy=${8:-false}
    
    # Initialize log file
    echo "============================================" > "$log_file"
    echo "Hierarchical hadd log - $(date)" >> "$log_file"
    echo "Dataset: $dataset_name" >> "$log_file"
    echo "Hierarchy levels: $hierarchy_levels" >> "$log_file"
    echo "Use scratch: $use_scratch" >> "$log_file"
    echo "Verbose copy: $verbose_copy" >> "$log_file"
    echo "============================================" >> "$log_file"
    echo "" >> "$log_file"
    
    # Convert space-separated list to array
    local -a file_array=($input_list)
    local total_files=${#file_array[@]}
    
    if [ $total_files -eq 0 ]; then
        echo "[$dataset_name] ERROR: No files to merge!" >&2
        return 1
    fi
    
    echo "[$dataset_name] Total files to merge: $total_files"
    echo "[$dataset_name] Hierarchy levels: $hierarchy_levels"
    
    # Calculate batch size for first level
    local batch_size=$(calculate_batch_size $total_files $hierarchy_levels)
    echo "[$dataset_name] Calculated batch size: $batch_size files per first-level batch"
    
    # Prepare working directory
    local work_dir="${scratch_dir}_work"
    mkdir -p "$work_dir"
    
    # Copy to scratch if requested
    local -a current_files=()
    if [ "$use_scratch" = "true" ]; then
        echo "[$dataset_name] Copying files to scratch directory: $scratch_dir"
        mkdir -p "$scratch_dir"
        
        local copy_count=0
        local display_interval=50
        if [ "$verbose_copy" = "true" ]; then
            display_interval=50  # Show every 50 files
        fi
        
        for file in "${file_array[@]}"; do
            if [ -f "$file" ]; then
                local basename=$(basename "$file")
                local scratch_file="$scratch_dir/${copy_count}_${basename}"
                cp "$file" "$scratch_file"
                current_files+=("$scratch_file")
                copy_count=$((copy_count + 1))
                
                if [ "$verbose_copy" = "true" ]; then
                    display_copy_progress $copy_count $total_files "$dataset_name" $display_interval
                fi
            fi
        done
        
        echo "[$dataset_name] Copied $copy_count files to scratch directory"
    else
        # Use original files directly
        current_files=("${file_array[@]}")
    fi
    
    # Start hierarchical merging
    local current_level=1
    local level_files=("${current_files[@]}")
    
    while [ ${#level_files[@]} -gt 1 ] && [ $current_level -le $hierarchy_levels ]; do
        echo ""
        echo "[$dataset_name] ========================================"
        echo "[$dataset_name] Level $current_level: Processing ${#level_files[@]} files"
        echo "[$dataset_name] ========================================"
        
        local -a next_level_files=()
        local batch_num=0
        local file_idx=0
        
        while [ $file_idx -lt ${#level_files[@]} ]; do
            # Collect files for this batch
            local -a batch_files=()
            local batch_count=0
            
            # Take up to batch_size files (or remaining files if less)
            while [ $batch_count -lt $batch_size ] && [ $file_idx -lt ${#level_files[@]} ]; do
                batch_files+=("${level_files[$file_idx]}")
                file_idx=$((file_idx + 1))
                batch_count=$((batch_count + 1))
            done
            
            # Create intermediate output file for this batch
            local intermediate_output="${work_dir}/level${current_level}_batch${batch_num}.root"
            
            # Merge this batch
            merge_batch_of_files "$intermediate_output" "$log_file" "${batch_files[*]}" "$dataset_name"
            
            if [ $? -ne 0 ]; then
                echo "[$dataset_name] ERROR: Failed to merge batch $batch_num at level $current_level" >&2
                rm -rf "$work_dir"
                if [ "$use_scratch" = "true" ]; then
                    rm -rf "$scratch_dir"
                fi
                return 1
            fi
            
            next_level_files+=("$intermediate_output")
            batch_num=$((batch_num + 1))
        done
        
        echo "[$dataset_name] Level $current_level complete: Created ${#next_level_files[@]} intermediate files"
        
        # Clean up previous level files if they were in work_dir
        if [ $current_level -gt 1 ]; then
            for f in "${level_files[@]}"; do
                if [[ "$f" == "${work_dir}"* ]]; then
                    rm -f "$f"
                fi
            done
        fi
        
        # Prepare for next level
        level_files=("${next_level_files[@]}")
        current_level=$((current_level + 1))
        
        # Adjust batch size for next level (can merge more files as we have fewer)
        # Use remaining levels to calculate new batch size
        local remaining_levels=$((hierarchy_levels - current_level + 1))
        if [ $remaining_levels -gt 0 ]; then
            batch_size=$(calculate_batch_size ${#level_files[@]} $remaining_levels)
            if [ $batch_size -lt 2 ]; then
                batch_size=2
            fi
        else
            # Last level: merge all remaining files
            batch_size=${#level_files[@]}
        fi
    done
    
    # Final merge or move
    echo ""
    echo "[$dataset_name] ========================================"
    echo "[$dataset_name] Creating final output file"
    echo "[$dataset_name] ========================================"
    
    if [ ${#level_files[@]} -eq 1 ]; then
        # Only one file left, just move it
        echo "[$dataset_name] Moving final file to destination"
        mv "${level_files[0]}" "$final_output"
    else
        # Need final merge
        echo "[$dataset_name] Final merge of ${#level_files[@]} files"
        merge_batch_of_files "$final_output" "$log_file" "${level_files[*]}" "$dataset_name"
        
        if [ $? -ne 0 ]; then
            echo "[$dataset_name] ERROR: Final merge failed" >&2
            rm -rf "$work_dir"
            if [ "$use_scratch" = "true" ]; then
                rm -rf "$scratch_dir"
            fi
            return 1
        fi
        
        # Clean up last level intermediate files
        for f in "${level_files[@]}"; do
            rm -f "$f"
        done
    fi
    
    # Cleanup
    echo "[$dataset_name] Cleaning up temporary files..."
    rm -rf "$work_dir"
    if [ "$use_scratch" = "true" ]; then
        rm -rf "$scratch_dir"
    fi
    
    echo "[$dataset_name] SUCCESS: Created $final_output"
    echo "" >> "$log_file"
    echo "============================================" >> "$log_file"
    echo "Merge completed successfully - $(date)" >> "$log_file"
    echo "============================================" >> "$log_file"
    
    return 0
}

###############################################################################
# Function: validate_hierarchy_config
# Validates hierarchy configuration parameters
#
# Arguments:
#   $1 - hierarchy levels
#
# Returns:
#   0 if valid, 1 if invalid
###############################################################################
function validate_hierarchy_config() {
    local levels=$1
    
    if ! [[ "$levels" =~ ^[0-9]+$ ]]; then
        echo "ERROR: HIERARCHY_LEVELS must be a positive integer" >&2
        return 1
    fi
    
    if [ $levels -lt 1 ]; then
        echo "ERROR: HIERARCHY_LEVELS must be >= 1" >&2
        return 1
    fi
    
    return 0
}

