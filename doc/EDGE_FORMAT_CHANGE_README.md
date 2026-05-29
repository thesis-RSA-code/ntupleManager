# Edge Format Change - Performance Optimization

**Date:** 2025-12-04  
**Issue:** Edge-to-flat conversion was 40x slower than hier-to-flat for large datasets

## Problem Identified

The original `convert_edge_to_flat.py` stored edges in HDF5 as `(2, N_edges)` and grew the dataset along axis-1 (columns). This caused O(n²) performance degradation because:

- HDF5 stores data in row-major (C-contiguous) order
- Resizing along axis-1 requires reorganizing existing data
- With 891K events and ~100M edges, each resize operation became progressively slower
- Result: **28 it/s** (would take ~9 hours) vs expected **1200 it/s** (4 minutes)

## Solution

**Changed edge storage from `(2, N_edges)` to `(N_edges, 2)`**

This allows resizing along axis-0 (rows), which is a simple append operation in HDF5.

Expected speedup: **40-50x** (matching hier-to-flat performance)

## Files Modified

### 1. **ntupleManager/convert_edge_to_flat.py**
- Changed: `dst.create_dataset('edges', shape=(0, 2), maxshape=(None, 2), ...)`
- Changed: Transpose input edges with `.T` before buffering
- Changed: Use `np.vstack()` instead of `np.hstack()`
- Changed: Resize along axis-0 instead of axis-1

### 2. **GhostHunter/src/datasets/flatten_hdf5_to_pyg.py**
- Updated edge loading to transpose: `self.dset_edges[e_start:e_end, :].T`
- Updated comment: Edges now stored as `(N_edges, 2)`

### 3. **mini-Caverns-benchmarks/benchmark_dataloaders.py**
- Updated edge loading in `ContiguousHDF5Dataset`: `edge_index[edge_start:edge_end, :].T`

## Impact & Next Steps

### ⚠️ Breaking Change
- Old `*_flat.h5` files use format `(2, N)`
- New `*_flat.h5` files use format `(N, 2)`
- **You must regenerate all flat edge files**

### Files to Regenerate

Run these conversions with the updated script:

```bash
# Test set (small - ~100K events)
cd /sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager
python convert_edge_to_flat.py \
  -i /sps/t2k/eleblevec/Datasets/custom_dataset/e-/50-1500MeV/Ndigit_40_1Mevents/test_1_a1000/h5_edges/knn3_xyz_cut_t900-1400_q03-1000_e-_50-1500MeV_folder1_a1000.h5 \
  -o /sps/t2k/eleblevec/Datasets/custom_dataset/e-/50-1500MeV/Ndigit_40_1Mevents/test_1_a1000/h5_edges/knn3_xyz_cut_t900-1400_q03-1000_e-_50-1500MeV_folder1_a1000_flat.h5

# Training set (large - ~900K events)
python convert_edge_to_flat.py \
  -i /sps/t2k/eleblevec/Datasets/custom_dataset/e-/50-1500MeV/Ndigit_40_1Mevents/train_val_1001_a10000/h5_edges/knn3_xyz_cut_t900-1400_q03-1000_e-_50-1500MeV_folder1001_a10000.h5 \
  -o /sps/t2k/eleblevec/Datasets/custom_dataset/e-/50-1500MeV/Ndigit_40_1Mevents/train_val_1001_a10000/h5_edges/knn3_xyz_cut_t900-1400_q03-1000_e-_50-1500MeV_folder1001_a10000_flat.h5
```

### Performance Expectations
- **Small dataset (98K events)**: ~2 minutes (was 4 min, should stay similar)
- **Large dataset (891K events)**: ~10-15 minutes (was would-be 9 hours!)

## Verification

After regeneration, verify the format:

```python
import h5py
with h5py.File('path/to/file_flat.h5', 'r') as f:
    print(f'edges shape: {f["edges"].shape}')  # Should be (N_edges, 2)
    print(f'edge_pointer length: {len(f["edge_pointer"])}')  # Should be N_events + 1
```

## Compatibility

- **Hierarchical format files**: No changes needed (different format entirely)
- **Flat format files**: Must be regenerated
- **PyG Data objects**: No impact - edges are always in `(2, N)` format in memory after transpose

