"""Saved hashed roster comparison; never parses private publisher files."""
import hashlib, json, math, re, struct

def require(ok, message):
    if not ok:
        raise ValueError(message)

def roster(raw):
    require(raw[:8] == b'CO2RSTR1' and len(raw) >= 12, 'roster schema')
    n = struct.unpack_from('<I', raw, 8)[0]
    require(n > 0 and len(raw) == 12+36*n, 'exact roster width')
    rows = {}; prev = None
    for off in range(12, len(raw), 36):
        key = raw[off:off+32]; count = struct.unpack_from('<I', raw, off+32)[0]
        require(count > 0 and (prev is None or key > prev), 'sorted unique fingerprints with positive multiplicity')
        rows[key] = count; prev = key
    return rows

def verify(readback, controls, source_raw, target_raw, tape5, tape6, selected_block):
    source = roster(source_raw); target = roster(target_raw)
    require(source == target, 'source and TAPE3 hashed field multisets differ')
    require(sum(source.values()) == 180771 and len(source) == 178430, 'declared full CO2 roster')
    for key, raw in [('public_source_roster', source_raw), ('public_TAPE3_roster', target_raw)]:
        r = readback[key]
        require(r['ordinary_lines'] == sum(source.values()) and r['unique_fingerprints'] == len(source), 'roster totals')
        require(hashlib.sha256(raw).hexdigest() == r['uncompressed_sha256'], 'raw hashed roster receipt')
        require(r['literal_publisher_scalar_records_included'] is False, 'roster is hashes only')
    require(readback['status'] == 'PASS_SCOPED_CO2_SOURCE_TO_TAPE3_ROSTER' and readback['range_cm1'] == [475.,2275.], 'held census scope')
    require(readback['source_count'] == readback['TAPE3_count'] == 180771 and readback['missing_count'] == readback['extra_count'] == 0, 'census totals')
    require(readback['source_projection_sha256'] == readback['TAPE3_projection_sha256'], 'root scalar projection digest')
    require(readback['source']['sha256'] == 'd0ec800cfaeaaa7ab7af7b8168f45b205e383272e147373df6d0eed2677f2bd3', 'held publisher input')
    t = readback['TAPE3']
    require(t['sha256'] == '56bd55fa256ed3b3a672bd4bcd88034cd7086d4fbef2a1def9480199dab2b388', 'held historical output')
    require(t['physical_records'] == 6259 and t['blocks'] == 3129 and t['ordinary_lines'] == 648464 and t['sidecar_records'] == 128015, 'full TAPE3 framing totals')
    require(t['species_counts']['2'] == 180771 and t['coupled_main_counts']['2'] == 127543, 'CO2 totals')
    expected_flags = {'1':127543,'0':53228}
    require(readback['source']['CO2_flags'] == t['CO2_flags'] == expected_flags, 'CO2 flag roster')
    a, b = readback['source_bins25cm1'], readback['TAPE3_bins25cm1']
    # These four source bins contain no CO2 ordinary record. Requiring an
    # occupied bin everywhere would invent source lines in a real gap.
    empty_bins = {1575,1600,1625,1650}
    require(a == b and set(a) == {str(n) for n in range(475,2275,25) if n not in empty_bins}, 'exact occupied bin roster')
    require(sum(row['ordinary'] for row in a.values()) == 180771 and sum(row['coupled'] for row in a.values()) == 127543, 'bin sum')
    require(all(0 <= row['coupled'] <= row['ordinary'] for row in a.values()), 'bin count bounds')
    # Join a member of the full roster to the previously included real TAPE3
    # block. This is not a full input read by saved CI.
    require(len(selected_block) == 39000, 'parent block width')
    i = 123; j = 124
    v = struct.unpack_from('<d', selected_block, 8*i)[0]
    mol = struct.unpack_from('<i', selected_block, 5000+4*i)[0]
    flag = struct.unpack_from('<i', selected_block, 9000+4*i)[0]
    floats = [struct.unpack_from('<f', selected_block, off+4*i)[0] for off in (3000,4000,6000,7000,8000)]
    require(v == 618.023668 and mol == 102 and flag == 1, 'selected line identity')
    projection = struct.pack('<diifffff',v,mol,flag,*floats)
    coeffs = [struct.unpack_from('<d',selected_block,8*j)[0]] + [struct.unpack_from('<f',selected_block,off+4*j)[0] for off in range(2000,9000,1000)]
    sf = struct.unpack_from('<i',selected_block,9000+4*j)[0]
    projection += struct.pack('<8fi',*coeffs,sf)
    fingerprint = hashlib.sha256(projection).digest()
    require(source.get(fingerprint) == 1, 'selected parent line belongs once to full hashed roster')
    require(readback['source']['selected']['pair_projection_sha256'] == t['selected']['pair_projection_sha256'] == fingerprint.hex(), 'selected root receipt')
    require((t['selected']['block_1based'],t['selected']['data_record_1based'],t['selected']['slot_1based']) == (260,521,124), 'selected record receipt')
    require(hashlib.sha256(tape5).hexdigest() == controls['LNFL_TAPE5_sha256'], 'actual TAPE5 pin')
    lines = tape5.decode('ascii').splitlines()
    require(lines[1] == '   475.000  2275.000' and lines[2][47:].strip() == '', 'actual default format switches')
    require([i+1 for i,x in enumerate(lines[2][:47]) if x=='1'] == [1,2,3,4,6,7,22], 'selected molecules')
    require(controls['F100'] is True and controls['NOCPL'] is False and controls['REJ_token'] is False, 'control interpretation')
    parsed = {}
    for line in tape6.decode('ascii').splitlines():
        m = re.match(r'\s*(\w+)\s*=\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s*$',line)
        if m:
            parsed[m[1]] = {'ordinary_lines':int(m[2]),'coupled_lines':int(m[3]),'strength_rejection':float(m[8].replace('D','E'))}
    require(parsed == controls['LNFL_strength_rejection'] and len(parsed)==22 and all(x['strength_rejection']==0 for x in parsed.values()), 'actual zero rejection fields')
    require(parsed['CO2']['ordinary_lines']==180771 and parsed['CO2']['coupled_lines']==127543, 'log to census join')
    for key in ('original_mixing_physical_partner_completeness_established','LBLRTM_layer_rejection_and_finite_support_validated','full_strength_normalization_replayed','physical_reference_accepted','production_accepted'):
        require(readback[key] is False, 'no physical/scope promotion: '+key)
    require(readback['full_source_and_TAPE3_read_by_root'] is True and readback['solver_or_compiler_processes']==0, 'root readback scope')
    require(controls['coupled_line_specific_runtime_inventory_observed'] is False and controls['physical_reference_accepted'] is False and controls['production_accepted'] is False, 'controls scope')
    return {'schema':'UDM37_SAVED_CO2_LNFL_ROSTER_COMPARISON_V1',
            'status':'PASS_SCOPED_CO2_SOURCE_TO_TAPE3_HASHED_FIELD_ROSTER',
            'CO2_ordinary_lines':180771,'CO2_coupled_main_lines':127543,
            'unique_field_fingerprints':178430,'preserves_duplicate_multiplicity':True,
            'empty_source_bins25cm1':[1575,1600,1625,1650],
            'missing_or_extra_projected_records':0,'LNFL_strength_rejection':0.,
            'selected_parent_TAPE3_member_exact':True,'raw_ASCII_or_full_TAPE3_reopened_by_saved_CI':False,
            'complete_strength_and_quantum_identity_verified':False,
            'original_mixing_physical_partner_completeness_established':False,
            'LBLRTM_layer_rejection_and_finite_support_validated':False,
            'physical_reference_accepted':False,'production_accepted':False}
