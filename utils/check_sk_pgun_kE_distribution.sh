#!/bin/bash

cd /sps/t2k/eleblevec/mini-Caverns-toolsbox/ntupleManager
source /sps/t2k/eleblevec/miniconda3/etc/profile.d/conda.sh && conda activate pt28_cuda129
D=/sps/t2k/eleblevec/Datasets/sk_iv/pgun_ccan/combined_e-_mu-_pi+/smoke_datasets/uniform_energy
HY=/sps/t2k/eleblevec/Datasets/sk_iv/pgun_ccan/combined_e-_mu-_pi+/multi_combine.hy

for P in mu- e-; do
  echo "=================== $P ==================="
  python hy_flat_to_hier_hdf5.py \
      --input  "$HY" \
      --output "$D/sk_pgun_ccan_${P}_uniform_1k.h5" \
      --indices-npz "$D/sk_pgun_ccan_${P}_uniform_1k_indices.npz" \
      --indices-key indices \
      --min-hit-charge 0.11 --max-hit-charge 51.0 2>&1 | tail -4
  python utils/verify_uniform_subset.py \
      --h5 "$D/sk_pgun_ccan_${P}_uniform_1k.h5" \
      --indices-npz "$D/sk_pgun_ccan_${P}_uniform_1k_indices.npz"
done