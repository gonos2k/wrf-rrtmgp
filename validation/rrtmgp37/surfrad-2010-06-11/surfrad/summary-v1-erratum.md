# Erratum: station-summary V1 unit labels

`station-summary-v1.json` is retained unchanged as the original inventory. Its index-based unit label incorrectly marked SURFRAD `dw_casetemp`, `dw_dometemp`, `uw_casetemp`, and `uw_dometemp` as W m⁻², and labeled `uvb` as W m⁻². NOAA's file README specifies the four case/dome temperatures in K and UVB in mW m⁻². Other values were not modified. Use `station-summary-v2.json` for correct per-variable units, great-circle distances, and the verified June 12 endpoint rows. Raw station files and their hashes are unchanged.
