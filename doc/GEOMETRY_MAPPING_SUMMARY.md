# Geometry Mapping Implementation Summary

## Overview
Successfully implemented a geometry mapping system to handle different detector simulations (HyperK, WCTE) with different ROOT variable names while maintaining consistent HDF5 output.

## Files Modified

### 1. `ntupleManager/root_to_hdf5.py`
**Changes:**
- Added import for geometry mapping functions
- Added `--geometry` command-line argument (default: "HyperK")
- Added geometry parameter to YAML config loading
- Integrated geometry mapping in data loading pipeline:
  - Translates standard HDF5 field names → ROOT field names
  - Validates loaded data for missing fields
  - Processes events using ROOT names, writes using standard HDF5 names
- Added geometry information to HDF5 metadata
- Enhanced error messages for vector validation

**Backward Compatibility:** ✅ YES
- Existing HyperK configs work without modification
- Default geometry is "HyperK"
- All existing YAML configs continue to work

## Files Created

### 2. `ntupleManager/utils/geometry_mappings.py` (NEW)
**Purpose:** Central mapping definitions for all geometries

**Key Components:**
- `GEOMETRY_MAPPINGS`: Dictionary containing mappings for each geometry
  - `'HyperK'`: Your original simulation variable names
  - `'WCTE'`: External collaborator's variable names
  
- `get_geometry_mapping(geometry_name)`: Retrieve mapping for a specific geometry

- `apply_geometry_mapping(fields_config, geometry_name)`: 
  - Translates HDF5 standard names → ROOT field names
  - Returns mapped config, fields to load, and missing fields
  - Issues warnings (not errors) for unavailable fields

- `validate_loaded_data(events_data, root_fields_to_load, geometry_name)`:
  - Validates that expected fields exist in loaded ROOT data
  - Issues warnings for missing fields
  - Returns list of available fields

**Field Handling:**
- Scalar fields: Direct name mapping
- Vector fields: Maps to 3D component lists with validation
- Missing fields: Set to `None`, triggers warning

### 3. `ntupleManager/configs/data_extraction_config_WCTE_example.yaml` (NEW)
**Purpose:** Example configuration for WCTE geometry

Shows how to:
- Specify geometry parameter
- Use standard field names (same as HyperK)
- System automatically handles name translation

### 4. `ntupleManager/utils/GEOMETRY_MAPPING_README.md` (NEW)
**Purpose:** Comprehensive documentation

Covers:
- System overview and key concepts
- Usage examples (CLI, YAML, defaults)
- How the mapping works (step-by-step)
- Missing field handling
- Adding new geometries
- Vector field validation
- Benefits and troubleshooting

## Variable Mappings

### HyperK → Standard (no change needed)
| Standard HDF5 Name | HyperK ROOT Name |
|-------------------|------------------|
| `n_digi_hits` | `n_digi_hits` |
| `energy` | `energy` |
| `event_type` | `event_type` |
| `trigger_time` | `trigger_time` |
| `vertex` | `vertex` |
| `particle_dir` | `particle_dir` |
| `particle_stop` | `particle_stop` |
| `particle_start` | `particle_start` |
| `charge` | `charge` |
| `time` | `time` |
| `hitx`, `hity`, `hitz` | `hitx`, `hity`, `hitz` |
| `dwall`, `towall` | `dwall`, `towall` |

### WCTE → Standard (mapping applied)
| Standard HDF5 Name | WCTE ROOT Name | Notes |
|-------------------|----------------|-------|
| `n_digi_hits` | `n_hits` | **Different** |
| `energy` | `energy` | Same |
| `event_type` | `eventType` | **camelCase** |
| `trigger_time` | `time_trigger` | **Different** |
| `vertex` | `vertex` | Same |
| `particle_dir` | `particleDir` | **camelCase** |
| `particle_stop` | `particleStop` | **camelCase** |
| `particle_start` | `None` | **Not available** ⚠️ |
| `charge` | `charge` | Same |
| `time` | `time` | Same |
| `hitx`, `hity`, `hitz` | `hitx`, `hity`, `hitz` | Same |
| `dwall`, `towall` | `dwall`, `towall` | Same |
| `hit_profile` | `hit_profile` | WCTE-specific ✨ |

## Behavior Examples

### Example 1: HyperK (Default)
```bash
python root_to_hdf5.py --config my_config.yaml
# Uses HyperK geometry (default)
# All field names pass through unchanged
```

### Example 2: WCTE with Missing Field
```bash
python root_to_hdf5.py --config wcte_config.yaml --geometry WCTE
```

Output:
```
Using geometry: WCTE
Applying geometry mapping...
UserWarning: Field 'particle_start' is not available in geometry 'WCTE'. It will be skipped.
Note: 1 field(s) not available in this geometry: ['particle_start']
Variables to load from ROOT file: ['n_hits', 'energy', 'eventType', ...]
Processing events: 100%|████████████████████| 1000/1000
Processing finished. 1000 events written to the HDF5 file.
```

### Example 3: Invalid Geometry
```bash
python root_to_hdf5.py --config my_config.yaml --geometry InvalidName
```

Output:
```
ValueError: Unknown geometry 'InvalidName'. Available geometries: HyperK, WCTE
```

## Data Flow

```
1. User Config (Standard HDF5 Names)
   ↓
2. Geometry Mapping Applied
   ↓
3. ROOT File (Geometry-Specific Names)
   ↓
4. Data Loading & Validation
   ↓
5. Processing Loop (Read: ROOT names, Write: Standard names)
   ↓
6. HDF5 Output (Standard HDF5 Names) ✨
```

## Key Features

✅ **Consistent Output**: All HDF5 files use identical field names  
✅ **Flexible Input**: Handles different ROOT file formats  
✅ **Warning System**: Missing fields trigger warnings, not errors  
✅ **Validation**: Vector fields must be 3D (raises error if not)  
✅ **Metadata**: Geometry name stored in HDF5 metadata  
✅ **Extensible**: Easy to add new geometries  
✅ **Backward Compatible**: Existing code unchanged  

## Testing Recommendations

1. **Test HyperK (Backward Compatibility)**
   ```bash
   python root_to_hdf5.py --config configs/data_extraction_config_e-_train_val_set.yaml
   # Should work exactly as before
   ```

2. **Test WCTE (New Geometry)**
   ```bash
   python root_to_hdf5.py --config configs/data_extraction_config_WCTE_example.yaml
   # Update paths in config first
   ```

3. **Test Missing Fields**
   - Include `particle_start` in WCTE config
   - Verify warning is issued but processing continues

4. **Verify HDF5 Output**
   - Check that both HyperK and WCTE produce identical field names
   - Verify geometry metadata is stored

## Adding New Geometries

To add a new geometry (e.g., "SuperK"):

1. Edit `utils/geometry_mappings.py`
2. Add new entry to `GEOMETRY_MAPPINGS`:
   ```python
   'SuperK': {
       'n_digi_hits': 'nhits',
       'energy': 'E_true',
       # ... map all standard fields
       'some_field': None,  # if not available
   }
   ```
3. Use in config: `geometry: "SuperK"`

## Questions?

See `ntupleManager/utils/GEOMETRY_MAPPING_README.md` for detailed documentation.

