"""Documentary and saved-spectrum boundaries; no model/solver execution."""
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from verify import verify

ROOT = Path(__file__).resolve().parents[3]
INDEX = json.loads(Path(__file__).with_name('checklist.json').read_text())


class AcceptanceBoundary(unittest.TestCase):
    def test_pinned_index_does_not_approve_production(self):
        result = verify(ROOT, INDEX)
        self.assertEqual(result['index_integrity'], 'PASS')
        self.assertFalse(result['production_accepted'])
        self.assertEqual(result['original_gates'], 19)

    def test_reject_missing_original_gate(self):
        index = copy.deepcopy(INDEX)
        index['original19'].pop()
        with self.assertRaisesRegex(ValueError, 'original19'):
            verify(ROOT, index)

    def test_reject_false_approval(self):
        index = copy.deepcopy(INDEX)
        index['production_accepted'] = True
        with self.assertRaisesRegex(ValueError, 'production acceptance'):
            verify(ROOT, index)

    def test_reject_changed_evidence_digest(self):
        index = copy.deepcopy(INDEX)
        index['evidence'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            verify(ROOT, index)

    def test_reject_path_escape(self):
        index = copy.deepcopy(INDEX)
        index['evidence'][0]['path'] = '../foreign-repository'
        with self.assertRaisesRegex(ValueError, 'unexpected evidence paths'):
            verify(ROOT, index)

    def test_reject_missing_evidence(self):
        index = copy.deepcopy(INDEX)
        index['evidence'].pop()
        with self.assertRaisesRegex(ValueError, 'evidence paths'):
            verify(ROOT, index)

    def test_reject_empty_runtime_roster(self):
        index = copy.deepcopy(INDEX)
        index['startup_runtime_source_sha256'] = {}
        with self.assertRaisesRegex(ValueError, 'startup runtime paths'):
            verify(ROOT, index)

    def test_source_change_is_reported_without_retagging_evidence(self):
        index = copy.deepcopy(INDEX)
        name = next(iter(index['startup_runtime_source_sha256']))
        index['startup_runtime_source_sha256'][name] = '0' * 64
        result = verify(ROOT, index)
        self.assertEqual(result['index_integrity'], 'PASS')
        self.assertFalse(result['startup_source_subset_matches'])
        self.assertFalse(result['production_accepted'])


class SavedNativeWindowIntegration(unittest.TestCase):
    def test_saved_native_window_and_negative_controls(self):
        # Existing CI entry point, separate from physical/index approval.
        package = ROOT / 'validation/rrtmgp37/lbl-native-spectral-window'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run(
                [sys.executable, '-I', '-S', str(package / name)],
                cwd=ROOT, capture_output=True, text=True, timeout=60)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class SavedResearchContractIntegration(unittest.TestCase):
    def test_research_profile_and_physical_approval_boundary(self):
        package = ROOT / 'validation/rrtmgp37/research-policy-contract'
        for name in ('verify_saved.py', 'test_contract.py'):
            proc = subprocess.run(
                [sys.executable, '-I', '-S', str(package / name)],
                cwd=ROOT, capture_output=True, text=True, timeout=60)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class SavedRadiationOccurrenceIntegration(unittest.TestCase):
    def test_actual_call_paths_and_post_capture_noninterference(self):
        package = ROOT / 'validation/rrtmgp37/radiation-occurrence-runtime'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run(
                [sys.executable, '-I', '-S', str(package / name)],
                cwd=ROOT, capture_output=True, text=True, timeout=60)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class SavedOmittedIceSensitivityIntegration(unittest.TestCase):
    def test_held_ice_effect_and_isolation_boundaries(self):
        package = ROOT / 'validation/rrtmgp37/omitted-ice-effect'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run(
                [sys.executable, '-I', '-S', str(package / name)],
                cwd=ROOT, capture_output=True, text=True, timeout=90)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class DryNumberCandidateIntegration(unittest.TestCase):
    def test_opt_in_number_candidate_and_saved_boundaries(self):
        package = ROOT / 'validation/rrtmgp37/dry-number-grid-v1'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run(
                [sys.executable, '-I', '-S', str(package / name)],
                cwd=ROOT, capture_output=True, text=True, timeout=90)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)



class SavedBoundaryMeltIntegration(unittest.TestCase):
    def test_current_boundary_and_melt_fix(self):
        package = ROOT / 'validation/rrtmgp37/boundary-melt-fix'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run([sys.executable, '-I', '-S', str(package / name)],
                                  cwd=ROOT, capture_output=True, text=True, timeout=60)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class PartialPopulationCandidateIntegration(unittest.TestCase):
    def test_actual_fixed_CF_population_and_final_joins(self):
        package = ROOT / 'validation/rrtmgp37/partial-population-candidate'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run([sys.executable, '-I', '-S', str(package / name)],
                                  cwd=ROOT, capture_output=True, text=True, timeout=60)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class WarmPopulationRuntimeIntegration(unittest.TestCase):
    def test_actual_integrated_exchange_and_checkpoint(self):
        package = ROOT / 'validation/rrtmgp37/warm-population-integration'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run([sys.executable, '-I', '-S', str(package / name)],
                                  cwd=ROOT, capture_output=True, text=True, timeout=60)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class CF0WarmTransitionIntegration(unittest.TestCase):
    def test_actual_transition_and_later_optics(self):
        package = ROOT / 'validation/rrtmgp37/cf0-warm-transition'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run([sys.executable, '-I', '-S', str(package / name)],
                                  cwd=ROOT, capture_output=True, text=True, timeout=60)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class Policy2BudgetOpticsStudyIntegration(unittest.TestCase):
    def test_retained_host_budgets_and_independent_optical_scope(self):
        package = ROOT / 'validation/rrtmgp37/policy2-budget-optics'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run([sys.executable, '-I', '-S', str(package / name)],
                                  cwd=ROOT, capture_output=True, text=True, timeout=90)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class ConsistentWarmInputStudyIntegration(unittest.TestCase):
    def test_consistent_input_budgets_and_matched_optical_scope(self):
        package = ROOT / 'validation/rrtmgp37/consistent-warm-input'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run([sys.executable, '-I', '-S', str(package / name)],
                                  cwd=ROOT, capture_output=True, text=True, timeout=90)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class HostSourceFixedPSDStudyIntegration(unittest.TestCase):
    def test_host_source_chain_and_fixed_mass_number_PSD(self):
        package = ROOT / 'validation/rrtmgp37/host-source-fixed-psd'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run([sys.executable, '-I', '-S', str(package / name)],
                                  cwd=ROOT, capture_output=True, text=True, timeout=90)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class AppliedRadiationEnergyStudyIntegration(unittest.TestCase):
    def test_actual_radiation_application_and_frozen_YSU_contract(self):
        package = ROOT / 'validation/rrtmgp37/applied-radiation-energy'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run([sys.executable, '-I', '-S', str(package / name)],
                                  cwd=ROOT, capture_output=True, text=True, timeout=90)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class NativeRadiationCapacityStudyIntegration(unittest.TestCase):
    def test_explicit_caloric_candidate_and_live_positive_Gamma8(self):
        package = ROOT / 'validation/rrtmgp37/native-radiation-capacity'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run([sys.executable, '-I', '-S', str(package / name)],
                                  cwd=ROOT, capture_output=True, text=True, timeout=90)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class ResearchRadiationIntegration(unittest.TestCase):
    def test_opt_in_radiation_combinations_and_between_call_restart(self):
        package = ROOT / 'validation/rrtmgp37/research-radiation-integration'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run([sys.executable, '-I', '-S', str(package / name)],
                                  cwd=ROOT, capture_output=True, text=True, timeout=90)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


class SustainedResearchIntegration(unittest.TestCase):
    def test_frozen_day_night_trajectory_and_evolved_restart(self):
        package = ROOT / 'validation/rrtmgp37/sustained-research'
        for name in ('verify_saved.py', 'test_saved.py'):
            proc = subprocess.run([sys.executable, '-I', '-S', str(package / name)],
                                  cwd=ROOT, capture_output=True, text=True, timeout=90)
            print(proc.stdout, end='')
            print(proc.stderr, end='')
            self.assertEqual(proc.returncode, 0, name)


if __name__ == '__main__':
    unittest.main()
