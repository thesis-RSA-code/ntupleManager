"""
Geometry-specific field mappings for different detector simulations.

This module defines how variable names from different ROOT file formats
should be mapped to standardized HDF5 field names.

Structure:
    GEOMETRY_MAPPINGS[geometry_name][standard_hdf5_name] = root_file_name
    
    - If root_file_name is None, the variable is not available in that geometry
    - If root_file_name is a string, it's the name to load from the ROOT file
"""

import warnings


# Mapping: {standard_hdf5_name: root_file_name}
GEOMETRY_MAPPINGS = {
    'HyperK': {
        # Scalar fields - event-level properties
        'n_digi_hits': 'n_digi_hits',
        'energy': 'energy',
        'event_type': 'event_type',
        'towall': 'towall',
        'dwall': 'dwall',
        'trigger_time': 'trigger_time',
        
        # Scalar fields - hit-level data (jagged arrays)
        "tube_ids": "tube_ids",
        'hitx': 'hitx',
        'hity': 'hity',
        'hitz': 'hitz',
        'pmt_charge': 'pmt_charge',
        'pmt_time': 'pmt_time',   
        'charge': 'pmt_charge', #backwards compatibility
        'time': 'pmt_time', #backwards compatibility
        
        # Vector fields - 3D vectors
        'vertex': ['vertex_x', 'vertex_y', 'vertex_z'],
        'particle_dir': ['particle_dir_x', 'particle_dir_y', 'particle_dir_z'],
        'particle_stop': ['particle_stop_x', 'particle_stop_y', 'particle_stop_z'],
        'particle_start': ['particle_start_x', 'particle_start_y', 'particle_start_z'],
        
        # Additional fields that might exist
        'hit_profile': None,  # Not available in HyperK
    },
    
    'WCTE': {
        # Scalar fields - event-level properties
        'n_digi_hits': 'n_hits',         # Different name in WCTE
        'energy': 'energy',
        'event_type': 'eventType',       # camelCase in WCTE
        'towall': 'towall',
        'dwall': 'dwall',
        'trigger_time': 'time_trigger',  # Different name in WCTE
        
        # Scalar fields - hit-level data (jagged arrays)
        'charge': 'charge',
        'time': 'time',
        'hitx': 'hitx',
        'hity': 'hity',
        'hitz': 'hitz',
        'pmt_charge': 'charge',          # Map to same field
        'pmt_time': 'time',              # Map to same field
        
        # Vector fields - 3D vectors
        'vertex': 'vertex',
        'particle_dir': 'particleDir',   # camelCase in WCTE
        'particle_stop': 'particleStop', # camelCase in WCTE
        'particle_start': None,          # Not available in WCTE
        
        # Additional fields
        # 'hit_profile': 'hit_profile',    # Available in WCTE
    },
}


def get_geometry_mapping(geometry_name):
    """
    Get the field mapping for a specific geometry.
    
    Args:
        geometry_name: Name of the geometry ('HyperK', 'WCTE', etc.)
        
    Returns:
        Dictionary mapping standard HDF5 field names to ROOT file field names
        
    Raises:
        ValueError: If geometry_name is not recognized
    """
    if geometry_name not in GEOMETRY_MAPPINGS:
        available = ', '.join(GEOMETRY_MAPPINGS.keys())
        raise ValueError(
            f"Unknown geometry '{geometry_name}'. "
            f"Available geometries: {available}"
        )
    
    return GEOMETRY_MAPPINGS[geometry_name]


def apply_geometry_mapping(fields_config, geometry_name, verbose=True):
    """
    Apply geometry mapping to a fields configuration.
    
    This function translates standard HDF5 field names to ROOT file field names
    based on the specified geometry. It handles missing fields gracefully.
    
    Args:
        fields_config: Dict with standard field names (HDF5 standard)
                      {root_field_name: root_field_name} for scalars
                      {root_field_name: [components]} for vectors
        geometry_name: Name of the geometry to use
        verbose: If True, print warnings for missing fields
        
    Returns:
        Tuple of (mapped_fields_config, root_fields_to_load, missing_fields)
        - mapped_fields_config: Dict mapping ROOT names to HDF5 output structure
        - root_fields_to_load: List of field names to load from ROOT file
        - missing_fields: List of fields that are not available in this geometry
    """
    geometry_mapping = get_geometry_mapping(geometry_name)
    
    mapped_config = {}
    root_fields_to_load = []
    missing_fields = []
    
    for root_field_name, target_hdf5_field_name in geometry_mapping.items():
        # Get the ROOT field name from geometry mapping
        # root_root_field_name = geometry_mapping.get(root_field_name, None)
        
        # Check if field is asked in the config 
        if root_field_name not in fields_config:
            missing_fields.append(root_field_name)
            if verbose:
                warnings.warn(
                    f"Field '{root_field_name}' is not available in root file'. "
                    f"It will be skipped.",
                    UserWarning
                )
            continue
        
        
        # Store the mapping: ROOT name -> HDF5 output structure
        if isinstance(target_hdf5_field_name, str):
            # Scalar field: map ROOT name to HDF5 name
            mapped_config[root_field_name] = target_hdf5_field_name
            root_fields_to_load.append(root_field_name)
        
        
        elif isinstance(target_hdf5_field_name, list):
            # Vector field: map ROOT name to component names
            # Verify it's a 3D vector
            if len(target_hdf5_field_name) != 3:
                raise ValueError(
                    f"3D field '{target_hdf5_field_name}' expected "
                    f"for {len(root_field_name)}, got {len(target_hdf5_field_name)}D "
                )
            # Store mapping: ROOT branch name -> HDF5 component names
            mapped_config[root_field_name] = target_hdf5_field_name
            root_fields_to_load.append(root_field_name)
    
    # Remove duplicates while preserving order
    # root_fields_to_load = list(dict.fromkeys(root_fields_to_load))
    print(f"DEBUG: root_fields_to_load: {root_fields_to_load}")
    
    return mapped_config, root_fields_to_load, missing_fields


def validate_loaded_data(events_data, root_fields_to_load, geometry_name, verbose=True):
    """
    Validate that all expected fields are present in the loaded data.
    
    Args:
        events_data: Awkward array with loaded data
        root_fields_to_load: List of field names that should be in the data
        geometry_name: Name of the geometry (for error messages)
        verbose: If True, print warnings for missing fields
        
    Returns:
        List of fields that are actually available
    """
    available_fields = []
    missing_in_data = []
    
    for root_field_name in root_fields_to_load:
        if root_field_name in events_data.fields:
            available_fields.append(root_field_name)
        else:
            missing_in_data.append(root_field_name)
            if verbose:
                warnings.warn(
                    f"Field '{root_field_name}' was expected in geometry '{geometry_name}' "
                    f"but not found in the ROOT file. It will be skipped.",
                    UserWarning
                )
    
    return available_fields, missing_in_data

