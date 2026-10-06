"""Ensure workspace support preserves the global frozen-mode initialization lock."""
import subprocess
import sys

result = subprocess.run([sys.argv[1], sys.argv[2], "flip", sys.argv[3]], capture_output=True, text=True)
assert result.returncode != 0, "frozen mode change was accepted"
assert "UDM frozen optics mode and table path must be global and unchanged" in result.stdout + result.stderr
print("WORKSPACE_FROZEN_MODE_LOCK_PASS")
