# Geometry Mapping System

## Overview

The geometry mapping system allows `root_to_hdf5.py` to handle ROOT files from different detector simulations that use different variable names. The system ensures that all HDF5 output files use **standardized field names**, regardless of the input geometry.

## Key Concepts

### Standard HDF5 Names (Output)
These are the **consistent** field names used in all HDF5 output files. They never change.

Examples:
- `n_digi_hits`, `energy`, `event_type`, `trigger_time`
- `vertex_x`, `vertex_y`, `vertex_z`
- `particle_dir_x`, `particle_dir_y`, `particle_dir_z`

### ROOT Field Names (Input)
These are the field names as they appear in the ROOT files. They **vary by geometry**.

Examples:
- HyperK: `n_digi_hits`, `trigger_time`, `particle_dir`
- WCTE: `n_hits`, `time_trigger`, `particleDir`

## Supported Geometries

### HyperK
Your original personal simulations. This is the default geometry.

### WCTE
External collaborator's simulations with different naming conventions.

## Usage

### Method 1: Command Line

```bash
python root_to_hdf5.py --config your_config.yaml --geometry WCTE
```

### Method 2: YAML Configuration File

Add the `geometry` parameter to your YAML config:

```yaml
geometry: "WCTE"
input_file: "/path/to/wcte/data.root"
output_file: "/path/to/output.h5"
# ... other config parameters
```

### Method 3: Default (HyperK)

If you don't specify a geometry, it defaults to HyperK:

```bash
python root_to_hdf5.py --config your_config.yaml
# Uses HyperK geometry by default
```

## How It Works

1. **Define Fields**: In your config, specify fields using standard HDF5 names
   ```yaml
   scalar_fields_config:
     - "charge"
     - "time"
   vector_fields_config:
     vertex: ["vertex_x", "vertex_y", "vertex_z"]
   ```

2. **Mapping**: The system looks up the ROOT field names for your geometry
   - HyperK: `vertex` → `vertex`
   - WCTE: `vertex` → `vertex` (same)
   - HyperK: `trigger_time` → `trigger_time`
   - WCTE: `trigger_time` → `time_trigger` (different!)

3. **Loading**: Data is loaded from ROOT using geometry-specific names

4. **Writing**: Data is saved to HDF5 using standard names (always consistent)

## Missing Fields

If a field is not available in a geometry:
- A **warning** is issued (not an error)
- The field is **skipped** (not saved to HDF5)
- Processing continues normally

Example:
```
UserWarning: Field 'particle_start' is not available in geometry 'WCTE'. It will be skipped.
```

## Adding a New Geometry

Edit `utils/geometry_mappings.py` and add a new entry to `GEOMETRY_MAPPINGS`:

```python
GEOMETRY_MAPPINGS = {
    'HyperK': { ... },
    'WCTE': { ... },
    'NewGeometry': {
        'n_digi_hits': 'num_hits',  # NewGeometry's name for n_digi_hits
        'energy': 'true_energy',    # NewGeometry's name for energy
        'vertex': 'vtx',            # NewGeometry's name for vertex
        'some_field': None,         # Not available in NewGeometry
        # ... etc
    }
}
```

## Vector Field Validation

All vector fields (vertex, particle_dir, particle_stop, etc.) **must be 3D**.

If a vector field is not 3D, the script will raise an error:
```
ValueError: Expected 3D vector for field 'vertex' (mapped from geometry 'WCTE'), but got shape (2,)
```

## Benefits

✅ **Consistent Output**: All HDF5 files use the same field names  
✅ **Easy Switching**: Change geometries with one parameter  
✅ **Backward Compatible**: Existing HyperK configs work without changes  
✅ **Graceful Degradation**: Missing fields don't break the pipeline  
✅ **Self-Documenting**: Geometry is stored in HDF5 metadata  

## Example Comparison

### HyperK Config (Before & After)
```yaml
# Works the same - backward compatible
geometry: "HyperK"  # Optional, this is the default
scalar_fields_config:
  - "charge"
```

### WCTE Config (New)
```yaml
# Same field names as HyperK config!
geometry: "WCTE"  # Only difference
scalar_fields_config:
  - "charge"  # Still use standard name
```

### Output (Always Consistent)
Both geometries produce HDF5 files with the same field names:
- `event_0/charge`
- `event_0/n_digi_hits`
- `event_0/vertex_x`, `vertex_y`, `vertex_z`

## Troubleshooting

### "Unknown geometry 'XYZ'"
The geometry name is not in `geometry_mappings.py`. Check spelling or add the new geometry.

### "Field 'X' is not available in geometry 'Y'"
This is a warning, not an error. The field will be skipped. If you need this field, either:
1. Add it to the geometry mapping (if it exists in ROOT with a different name)
2. Remove it from your config (if it doesn't exist at all)

### "Expected 3D vector but got shape (X,)"
A vector field is not actually a 3D vector. Check your ROOT file structure.

