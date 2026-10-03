#!/usr/bin/env python3
"""Extract production startup blocks, compile them in a minimal tile fixture."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
DRIVER = REPO / "WRF/phys/module_microphysics_driver.F"
UDM = REPO / "WRF/phys/module_mp_udm.F"
TEMPLATE = HERE / "ccn_startup_fixture.f90.in"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def extract_if_block(source: str, start_pattern: str) -> str:
    lines = source.splitlines()
    start = next((i for i, line in enumerate(lines) if re.search(start_pattern, line, re.I)), None)
    if start is None:
        raise AssertionError(f"production IF block not found: {start_pattern}")
    depth = 0
    for end in range(start, len(lines)):
        line = lines[end].split("!", 1)[0]
        if re.search(r"\bthen\s*$", line, re.I):
            depth += 1
        if re.search(r"\bendif\b", line, re.I):
            depth -= 1
            if depth == 0:
                return "\n".join(lines[start:end + 1])
    raise AssertionError(f"unterminated production IF block: {start_pattern}")

def extract_udm_initializer(source: str) -> str:
    lines = source.splitlines()
    start = next((i for i, line in enumerate(lines) if re.search(r"^\s*initialize_ccn\s*=\s*\.true\.\s*$", line, re.I)), None)
    if start is None:
        raise AssertionError("production initialize_ccn default not found")
    # Include the following logical expression and full-domain reset IF/loop.
    depth = 0
    entered = False
    for end in range(start, len(lines)):
        line = lines[end].split("!", 1)[0]
        if re.search(r"\bthen\s*$", line, re.I):
            depth += 1
            entered = True
        if re.search(r"\bendif\b", line, re.I):
            depth -= 1
            if entered and depth == 0:
                return "\n".join(lines[start:end + 1])
    raise AssertionError("production UDM initializer IF block unterminated")

class StartupFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver_text = DRIVER.read_text()
        cls.udm_text = UDM.read_text()
        cls.driver_block = extract_if_block(
            cls.driver_text, r"IF\s*\(\s*have_udm_cf\s*\.AND\.\s*itimestep\s*==\s*1"
        )
        cls.udm_block = extract_udm_initializer(cls.udm_text)
        template = TEMPLATE.read_text()
        cls.generated = template.replace("@@DRIVER_INIT_BLOCK@@", cls.driver_block).replace("@@UDM_INIT_BLOCK@@", cls.udm_block)
        if "@@DRIVER_INIT_BLOCK@@" in cls.generated or "@@UDM_INIT_BLOCK@@" in cls.generated:
            raise AssertionError("fixture template injection failed")

    def test_extracted_blocks_are_the_compiled_blocks(self):
        self.assertIn(self.driver_block, self.generated)
        self.assertIn(self.udm_block, self.generated)
        self.assertIn("QNN_CURR(ims:ime,kms:kme,jms:jme) = ccn_conc", self.driver_block)
        self.assertIn("PRESENT( RAINNCV )", self.driver_block)
        self.assertIn("if (present(ccn_preinitialized)) initialize_ccn = .not. ccn_preinitialized", self.udm_block)
        self.assertIn("nn(i,k,j) = ccn0", self.udm_block)
        # The actual option-37 call passes the explicit skip flag; the legacy call does not.
        self.assertIn(",ccn_preinitialized=.true.", self.driver_text.lower().replace(" ", ""))
        print("SOURCE_SHA256", sha(DRIVER), sha(UDM), "GENERATED_FIXTURE_SHA256", hashlib.sha256(self.generated.encode()).hexdigest())

    def test_gfortran_o0_o2_omp1_omp2(self):
        compiler = shutil.which("gfortran")
        if compiler is None:
            self.skipTest("gfortran is required for the standalone Fortran fixture")
        scratch = REPO / ".ccn-startup-test-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        try:
          for opt in ("0", "2"):
            with self.subTest(optimization=opt), tempfile.TemporaryDirectory(prefix="udm-ccn-fixture-", dir=scratch) as tmp:
                source = Path(tmp) / "ccn_startup_fixture.f90"
                exe = Path(tmp) / "ccn_startup_fixture"
                source.write_text(self.generated)
                compile_result = subprocess.run([
                    compiler, "-std=f2008", "-Wall", "-Wextra", "-fcheck=all", "-ffree-line-length-none",
                    "-fopenmp", f"-O{opt}", str(source), "-o", str(exe)
                ], check=False, capture_output=True, text=True)
                self.assertEqual(compile_result.returncode, 0, compile_result.stdout + compile_result.stderr)
                for threads in ("1", "2"):
                    env = os.environ.copy()
                    env.update(OMP_NUM_THREADS=threads, OMP_DYNAMIC="FALSE")
                    run = subprocess.run([str(exe)], env=env, check=False, capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    self.assertEqual(run.stdout.count("PASS "), 7, run.stdout)
                    self.assertNotIn("FAIL ", run.stdout)
        finally:
            scratch.rmdir()

if __name__ == "__main__":
    unittest.main()
