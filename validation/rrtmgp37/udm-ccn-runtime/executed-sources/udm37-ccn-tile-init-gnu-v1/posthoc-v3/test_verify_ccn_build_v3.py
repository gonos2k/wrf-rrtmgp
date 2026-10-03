#!/usr/bin/env python3
"""Offline negative controls for the separated WRF CPP/Fortran flag audit."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("verify_ccn_build_v3", HERE / "verify_ccn_build_v3.py")
verify = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(verify)


def log_fixture(cpp_flags="-DDM_PARALLEL -D_OPENMP", fortran_flags="-fopenmp"):
    lines = []
    for name in verify.MODULES:
        lines.extend([
            f"sed source {name}.F > {name}.G",
            f"/lib/cpp -P {cpp_flags} {name}.G > {name}.bb",
            f"standard.exe {name}.bb | /lib/cpp -P > {name}.f90",
            f"time mpif90 -o {name}.o -c {fortran_flags} {name}.f90",
        ])
    return "\n".join(lines)


class CompilePhaseFlagsTests(unittest.TestCase):
    def test_phase_correct_flags_pass(self):
        result = verify.verify_compile_phases(log_fixture())
        self.assertEqual(result["status"], "CPP_AND_FORTRAN_FLAGS_PASS")
        self.assertEqual(len(result["modules"]), 2)

    def test_cpp_dm_macro_missing_fails_even_with_mpi_fortran_wrapper(self):
        with self.assertRaisesRegex(ValueError, "CPP/Fortran flag phase check failed"):
            verify.verify_compile_phases(log_fixture(cpp_flags="-D_OPENMP"))

    def test_cpp_openmp_macro_missing_fails(self):
        with self.assertRaisesRegex(ValueError, "CPP/Fortran flag phase check failed"):
            verify.verify_compile_phases(log_fixture(cpp_flags="-DDM_PARALLEL"))

    def test_fortran_openmp_flag_missing_fails_even_if_cpp_has_macro(self):
        with self.assertRaisesRegex(ValueError, "CPP/Fortran flag phase check failed"):
            verify.verify_compile_phases(log_fixture(fortran_flags="-O2"))

    def test_flags_on_wrong_phase_do_not_pass(self):
        wrong = "\n".join([
            "sed source module_mp_udm.F > module_mp_udm.G",
            "/lib/cpp -P -D_OPENMP module_mp_udm.G > module_mp_udm.bb",
            "time mpif90 -o module_mp_udm.o -c -fopenmp -DDM_PARALLEL module_mp_udm.f90",
            "sed source module_microphysics_driver.F > module_microphysics_driver.G",
            "/lib/cpp -P -D_OPENMP module_microphysics_driver.G > module_microphysics_driver.bb",
            "time mpif90 -o module_microphysics_driver.o -c -fopenmp -DDM_PARALLEL module_microphysics_driver.f90",
        ])
        with self.assertRaisesRegex(ValueError, "CPP/Fortran flag phase check failed"):
            verify.verify_compile_phases(wrong)

    def test_actual_preserved_compiler_log_passes(self):
        task = HERE.parent
        actual = (task / "build-em_real-v1.log").read_text(errors="replace")
        result = verify.verify_compile_phases(actual)
        self.assertEqual(result["status"], "CPP_AND_FORTRAN_FLAGS_PASS")
        self.assertEqual(result["modules"]["module_mp_udm"]["phase_lines"], {
            "sed": 3817, "cpp": 3818, "standard_to_f90": 3819, "fortran_compile": 3821
        })
        self.assertEqual(result["modules"]["module_microphysics_driver"]["phase_lines"], {
            "sed": 5259, "cpp": 5260, "standard_to_f90": 5262, "fortran_compile": 5266
        })

    def test_wrong_phase_order_fails(self):
        wrong = "\n".join([
            "sed source module_mp_udm.F > module_mp_udm.G",
            "standard.exe module_mp_udm.bb | /lib/cpp > module_mp_udm.f90",
            "/lib/cpp -DDM_PARALLEL -D_OPENMP module_mp_udm.G > module_mp_udm.bb",
            "mpif90 -o module_mp_udm.o -c -fopenmp module_mp_udm.f90",
        ])
        with self.assertRaisesRegex(ValueError, "CPP/Fortran flag phase check failed"):
            verify.verify_compile_phases(wrong, ("module_mp_udm",))


if __name__ == "__main__":
    unittest.main(verbosity=2)
