import unittest
from parse_existing_logs import parse_line, phase_rows, validate_record_identities

ROW = 'LW RRTMGP_UDM_CF0_OMITTED phase=RAIN tile_i=1:37 tile_j=1:15 layers=616 sum_layer_grid_wp_g_m2= 4.285970E+02 max_layer_grid_wp_g_m2= 1.377294E+01'

class ParserControls(unittest.TestCase):
    def test_actual_source_format(self):
        r = parse_line(ROW)
        self.assertEqual(r['fields']['sum_layer_grid_wp_g_m2'], 428.597)
        self.assertEqual(r['fields']['tile_i'], [1, 37])

    def test_malformed_numeric(self):
        with self.assertRaises(ValueError): parse_line(ROW.replace('4.285970E+02', 'nan'))

    def test_missing_field(self):
        with self.assertRaises(ValueError): parse_line(ROW.split(' max_layer')[0])

    def test_duplicate_field(self):
        with self.assertRaises(ValueError): parse_line(ROW + ' layers=616')

    def test_duplicate_record_identity(self):
        r = dict(parse_line(ROW), rank=0, line=12)
        with self.assertRaises(ValueError): validate_record_identities([r, r])

    def test_repeated_values_at_distinct_lines_are_valid_calls(self):
        r = dict(parse_line(ROW), rank=0, line=12)
        validate_record_identities([r, dict(r, line=13)])

    def test_phases_not_mixed(self):
        lw, sw = parse_line(ROW), parse_line(ROW.replace('LW ', 'SW '))
        rows = [lw, sw]
        self.assertEqual(len(phase_rows(rows, 'LW', 'RAIN')), 1)
        self.assertEqual(len(phase_rows(rows, 'SW', 'RAIN')), 1)

if __name__ == '__main__': unittest.main()
