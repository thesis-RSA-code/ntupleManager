
"""
Standalone data extraction program that reads ROOT files and saves all data to HDF5.
This separates data extraction from graph building.
"""

import os
import sys  
import argparse
from pathlib import Path
import time


import awkward as ak
import uproot
import numpy as np

import psutil
from tqdm import tqdm

from utils.hdf5_writer import HDF5GraphWriter
from utils.funct_utils import load_config, print_summary
from utils.geometry_mappings import apply_geometry_mapping, validate_loaded_data


def load_data(file_path, tree_name, feature_vars, step_size="700MB"):
    """
    Returns an iterator and total entries to allow chunked processing.
    """
    print(f"Opening '{file_path}' (tree: '{tree_name}') with chunk size {step_size}...")
    
    # We open without 'with' here because the iterator needs the file to stay open
    file = uproot.open(file_path)
    tree = file[tree_name]
    total_entries = tree.num_entries
    
    # Returns the iterator, total count, and the file handle (to close later)
    return tree.iterate(feature_vars, step_size=step_size, library="ak"), total_entries, file

def determine_array_type(array):
    """
    Returns 'scalar' if 1 value per event, 'hit' if array of values per event.
    """
    # Check the type of the awkward array
    t = str(ak.type(array))
    # If the type indicates a variable length list (e.g. "25000 * var * float32")
    if "var *" in t:
        return 'hit'
    # If it is fixed dimension (e.g. "25000 * float32" or "25000 * 3 * float32")
    return 'scalar'

# Define scalar and vector fields configuration
default_scalar_fields = [
    'n_digi_hits', 'energy', 'event_type', 'towall', 'dwall', 'trigger_time'
]

default_vector_fields_config = {
    'vertex': ['vertex_x', 'vertex_y', 'vertex_z'],
    'particle_dir': ['particle_dir_x', 'particle_dir_y', 'particle_dir_z']
}

def main(args):
    # Validation des arguments 
    if not args.input_file.exists():
        raise FileNotFoundError(f"The input file was not found : {args.input_file}")
    
    # Get geometry name (default to 'HyperK')
    geometry_name = getattr(args, 'geometry', 'HyperK')
    print(f"Using geometry: {geometry_name}")
    
    fields_config = config.get('field_config', None)
    
    # Apply geometry mapping to translate HDF5 standard names to ROOT file names
    print("\nApplying geometry mapping...")
    mapped_fields_config, root_fields_to_load, missing_fields = apply_geometry_mapping(
        fields_config, 
        geometry_name,
        verbose=True
    )

    print(f"DEBUG: mapped_fields_config: {mapped_fields_config}")
    print(f"Variables to load from ROOT file: {root_fields_to_load}")    
    if missing_fields:
        print(f"Note: {len(missing_fields)} field(s) not available in this geometry: {missing_fields}")
    
    all_vars_to_load = root_fields_to_load  # These are ROOT file field names
    
    WriterClass = HDF5GraphWriter if args.storage_mode == "hierarchical" else HDF5GraphWriter
    
    # --- We ensure that the parent directory of the output file exists ---
    args.output_file.parent.mkdir(parents=True, exist_ok=True)

    # Initialization of the monitoring
    monitoring_results = {}
    process = psutil.Process(os.getpid()) if args.monitor_ram else None

    total_start_time = time.time()
    
    # --- Step 1: Data Loading (Initialization) ---
    if args.monitor_ram:
        monitoring_results['ram_before_load'] = process.memory_info().rss / 1024**2

    loading_start_time = time.time()
    
    # Get the iterator instead of a full array
    # Defaulting to 1GB chunks - this is what prevents OOM
    if not args.uproot_step_size.endswith("B"):
        uproot_step_size = int(args.uproot_step_size)
    
    print(f"Using uproot step size: {uproot_step_size}" )
    chunks_iterator, total_events, root_file_handle = load_data(
        args.input_file, args.tree_name, all_vars_to_load, step_size=uproot_step_size
    )
    
    loading_end_time = time.time()
    monitoring_results['loading_time'] = loading_end_time - loading_start_time
    
    # Track RAM after the first chunk is ready (initial overhead)
    if args.monitor_ram:
        monitoring_results['ram_after_load'] = process.memory_info().rss / 1024**2
        monitoring_results['ram_during_loop'] = []

    # --- Step 2: Processing and Writing ---
    print(f"\nDébut du traitement et de l'écriture de {total_events} événements...")
    processing_start_time = time.time()
    
    global_event_idx = 0
    written_count = 0

    with WriterClass(args.output_file, compression=args.compression) as writer:
        writer.add_metadata(
            source_file=str(args.input_file),
            tree_name=args.tree_name,
            geometry=geometry_name,
            fields_config=str(fields_config),
        )

        with tqdm(total=total_events, desc="Processing events") as pbar:
            for chunk in chunks_iterator:
                # Process each event in the current chunk
                for event in chunk:
                    # Keep your original RAM monitoring logic
                    if args.monitor_ram and global_event_idx % args.monitor_interval == 0:
                        current_ram = process.memory_info().rss / 1024**2
                        monitoring_results['ram_during_loop'].append((global_event_idx, current_ram))

                    # Original hit skipping logic
                    n_hits_root_name = "n_digi_hits"
                    if event[n_hits_root_name] == 0:
                        global_event_idx += 1
                        pbar.update(1)
                        continue
                
                    # Original data extraction logic
                    event_data = {}
                    for root_field_name, hdf5_output_structure in mapped_fields_config.items():
                        if root_field_name not in event.fields:
                            continue
                        
                        if isinstance(hdf5_output_structure, str):
                            event_data[hdf5_output_structure] = ak.to_numpy(event[root_field_name])
                        elif isinstance(hdf5_output_structure, list):
                            vector_data = ak.to_numpy(event[root_field_name])
                            for i, component_name in enumerate(hdf5_output_structure):
                                event_data[component_name] = vector_data[..., i]

                    # Write the event
                    writer.write_event(event_idx=global_event_idx, **event_data)
                    
                    global_event_idx += 1
                    written_count += 1
                    pbar.update(1)

    # Cleanup the ROOT file handle
    root_file_handle.close()

    # --- Step 3: Finalize Monitoring ---
    processing_end_time = time.time()
    total_end_time = time.time()
    
    monitoring_results['processing_time'] = processing_end_time - processing_start_time
    monitoring_results['total_time'] = total_end_time - total_start_time
            
    print(f"\nProcessing finished. {written_count} events written to the HDF5 file.")

    # # Tracking of the data loading memory usage
    # if args.monitor_ram:
    #     monitoring_results['ram_before_load'] = process.memory_info().rss / 1024**2


    # # Time the data loading
    # loading_start_time = time.time()
    # events_data = load_data(args.input_file, args.tree_name, all_vars_to_load)
    # loading_end_time = time.time()
    # monitoring_results['loading_time'] = loading_end_time - loading_start_time
    
    # # Validate that expected fields are present in the loaded data
    # available_fields, missing_in_data = validate_loaded_data(
    #     events_data, 
    #     root_fields_to_load, 
    #     geometry_name,
    #     verbose=True
    # )
    
    # if args.monitor_ram:
    #     monitoring_results['ram_after_load'] = process.memory_info().rss / 1024**2
    #     monitoring_results['ram_during_loop'] = []

    # # --- Step 2: Processing and Writing to the HDF5 file ---
    # print(f"\nDébut du traitement et de l'écriture dans '{args.output_file}'...")
    
    # # Time the processing loop
    # processing_start_time = time.time()
    
    # # --- CHANGEMENT: On utilise un contexte `with` pour gérer le fichier HDF5 ---
    # with WriterClass(args.output_file, compression=args.compression) as writer:

    #     # Store metadata including geometry information
    #     writer.add_metadata(
    #         source_file=str(args.input_file),
    #         tree_name=args.tree_name,
    #         geometry=geometry_name,
    #         fields_config=str(fields_config),  # Standard HDF5 field names
    #     )

    #     for event_idx, event in enumerate(tqdm(events_data, desc="Processing events")):
    #         if args.monitor_ram and event_idx % args.monitor_interval == 0:
    #             current_ram = process.memory_info().rss / 1024**2
    #             monitoring_results['ram_during_loop'].append((event_idx, current_ram))

    #         # Skip events with no hits (find ROOT field name that maps to 'n_digi_hits')
    #         n_hits_root_name = "n_digi_hits"

    #         if event[n_hits_root_name] == 0:
    #             continue
        
    #         # Extract data: read from ROOT field names, write to HDF5 standard names
    #         event_data = {}
    #         for root_field_name, hdf5_output_structure in mapped_fields_config.items():
    #             # Skip if field is not in this event (already validated earlier)
    #             if root_field_name not in event.fields:
    #                 continue
                
    #             if isinstance(hdf5_output_structure, str):
    #                 # Scalar field: ROOT name -> HDF5 standard name
    #                 hdf5_field_name = hdf5_output_structure
    #                 event_data[hdf5_field_name] = ak.to_numpy(event[root_field_name])
                
    #             elif isinstance(hdf5_output_structure, list):
    #                 # Vector field - decompose into components with HDF5 standard component names
    #                 vector_data = ak.to_numpy(event[root_field_name])
                    
    #                 # Validate that it's actually a 3D vector
    #                 if len(vector_data.shape) < 1 or (len(vector_data.shape) > 1 and vector_data.shape[-1] != 3):
    #                     raise ValueError(
    #                         f"Expected 3D vector for field '{root_field_name}' "
    #                         f"(mapped from geometry '{geometry_name}'), "
    #                         f"but got shape {vector_data.shape}"
    #                     )
                    
    #                 # Decompose into components
    #                 for i, component_name in enumerate(hdf5_output_structure):
    #                     event_data[component_name] = vector_data[..., i]

    #         # Write all data using standard HDF5 field names
    #         writer.write_event(
    #             event_idx=event_idx,
    #             **event_data  # All data uses standard HDF5 names
    #         )

    
    # # End timing measurements
    # processing_end_time = time.time()
    # total_end_time = time.time()
    
    # monitoring_results['processing_time'] = processing_end_time - processing_start_time
    # monitoring_results['total_time'] = total_end_time - total_start_time
            
    # print(f"\nProcessing finished. {len(events_data)} events written to the HDF5 file.")
    # print(f"Output file: {args.output_file}")
    
    # --- Step 3: Displaying the final summary ---
    if args.monitor_ram:
        final_ram = process.memory_info().rss / 1024**2
        monitoring_results['ram_during_loop'].append((global_event_idx, final_ram))
        print_summary(monitoring_results, args)
        np.savez(args.output_file.parent / "extraction_monitoring.npz", **monitoring_results)
    else:
        # Print timing summary even without RAM monitoring
        print_summary(monitoring_results, args)


def _normalize_detector(name: str) -> str:
    aliases = {"HK": "HyperK", "HYPERK": "HyperK", "WCTE": "WCTE"}
    return aliases.get(name.upper(), name)


if __name__ == "__main__":
    
    # Load YAML config if provided
    parser = argparse.ArgumentParser(description="Extraire les données des fichiers ROOT et les sauvegarder en HDF5.")
    parser.add_argument("--config", type=Path, help="Path to YAML configuration file (overrides other arguments).")
    parser.add_argument(
        "--detector",
        "--geometry",
        dest="detector",
        type=str,
        default="HyperK",
        help="Detector schema: HyperK (HK FD) or WCTE. Alias for --geometry.",
    )
    parsed_args = parser.parse_args()
    parsed_args.detector = _normalize_detector(parsed_args.detector)
    parsed_args.geometry = parsed_args.detector

    if parsed_args.config:
        config = load_config(parsed_args.config)
        
        # Override command line arguments with config values
        parsed_args.input_file = Path(config['input_file'])
        parsed_args.output_file = Path(config['output_file'])
        parsed_args.tree_name = config.get('tree_name', 'pure_root_tree')
        parsed_args.detector = _normalize_detector(config.get('geometry', parsed_args.detector))
        parsed_args.geometry = parsed_args.detector
        parsed_args.scalar_fields_config = config.get('scalar_fields_config', None)
        parsed_args.vector_fields_config = config.get('vector_fields_config', None)
        parsed_args.storage_mode = config.get('storage_mode', 'hierarchical')
        parsed_args.compression = config.get('compression', 'gzip')
        parsed_args.monitor_ram = config.get('monitor_ram', False)
        parsed_args.monitor_interval = config.get('monitor_interval', 10)
        parsed_args.uproot_step_size = config.get('uproot_step_size', "100MB")
        config['field_config'] = config.get('field_config', [])

    if parsed_args.detector == "WCTE":
        from root_to_hier_hdf5_wcte import convert

        convert(
            input_file=parsed_args.input_file,
            output_file=parsed_args.output_file,
            tree_name=getattr(parsed_args, "tree_name", "pure_root_tree"),
            step_size=str(getattr(parsed_args, "uproot_step_size", "200MB")),
            compression=getattr(parsed_args, "compression", "gzip"),
        )
    else:
        if not parsed_args.config:
            parser.error("HK/HyperK conversion requires --config YAML (or use root_to_hier_hdf5_wcte.py for WCTE).")
        main(parsed_args)
