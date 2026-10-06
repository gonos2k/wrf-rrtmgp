# Old versus expanded frozen-optics lookup in the prior coverage range

This is a read-only lookup comparison against saved direct midpoint generation. No Mie build, generator, or model was run for this analysis. The numerical differences are diagnostics, not physical accuracy criteria or forecast errors.

Coverage tested: 25 direct midpoint temperatures from 182.5 to 297.5 K, restricted to the old 180–300 K range; 9 lambdas, 16 bands, four moments (3600 samples per moment).

Old result/table SHA256: `c5116f4a3bb4e77dc8bed481ce52c07b29ee5f8d65fa6a5657a324c51e9a619c` / `8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583`.
Expanded result/table SHA256: `97378781c5cdfbe0ddbfc7f9dd739a325e2506efb454673a53028a5ad8cf8ae9` / `ebeafb9746164d5414a45eab4061c5c855f0f91e92be77003b3829722514fe6a`.
Direct-midpoint result/table SHA256: `35c6b1e9c5f1ba6ce877750f7658e39d0299a18c27334fa46145ed35b773460f` / `79a2e3b64dd5fa3affc9ed17bc19336505557acabf1f8c9507c5f53f0bc5f180`.
Kernel binaries (old/expanded/direct): `443a194ca4d7f530e7c38e717c33cd39c71c4d3215b27b4f0ea219c02f3cb858` / `6a0a5276ebcca55f1111aadb863c6c2706f4c413117dd16d2a604433340e6001` / `7a8259931bd782cbf45aa793f849aa3406b5aee2f350773fbe8c92a5b7af6632`. Each is checked against its own generation receipt; cross-directory byte identity is not required.

| Moment | Old lookup max abs normalized | Expanded lookup max abs normalized | Change max abs normalized | New lookup error lower / equal |
|---|---:|---:|---:|---:|
| extinction | 0.000328443665 | 4.30726253e-06 | 0.000325380597 | 3600 / 0 |
| scattering | 0.000397957991 | 5.36100036e-06 | 0.000394246547 | 3600 / 0 |
| scatter_times_g | 0.00024897982 | 3.50422343e-06 | 0.000246654204 | 3600 / 0 |
| absorption | 0.000261054365 | 3.54163534e-06 | 0.000258616148 | 3600 / 0 |

Absolute moment differences are also reported in m⁻¹; each moment’s maximum, mean, and RMS, and every per-temperature/lambda/band value are in [`old-vs-expanded-overlap-diagnostic.json.gz`](old-vs-expanded-overlap-diagnostic.json.gz).

The expanded axis changes interpolation inside the old range as well as adding low-temperature coverage. These measurements describe only the sampled lookup against the same numerical Mie reference. They do not validate the fixed refractive index, particle model, WRF response, or forecast accuracy.
