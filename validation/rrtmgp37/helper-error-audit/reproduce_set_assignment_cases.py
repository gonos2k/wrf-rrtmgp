"""Reproduce narrow set_assignment parser cases without importing WRF/model code."""
import ast
import hashlib
import json
import re
from pathlib import Path

source = Path("build/udm37-helper-errors-pr-work/WRF/test/rrtmgp/test_udm_startup_snow_scm.py")
tree = ast.parse(source.read_text())
function = next(node for node in tree.body
                if isinstance(node, ast.FunctionDef) and node.name == "set_assignment")
namespace = {"re": re, "fail": lambda message: (_ for _ in ()).throw(ValueError(message))}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
set_assignment = namespace["set_assignment"]
cases = {
    "indexed_scalar_lhs": ("&physics\n ra_lw_physics(1)=4,\n /\n", "ra_lw_physics", "37", "physics"),
    "indexed_slice_lhs": ("&physics\n ra_lw_physics(1:2)=4,5,\n /\n", "ra_lw_physics", "37", "physics"),
    "same_line_extra_rhs_value": ("&physics\n ra_lw_physics=4, 5,\n other=9,\n /\n", "ra_lw_physics", "37", "physics"),
    "continued_extra_rhs_value": ("&physics\n ra_lw_physics=4,\n 5,\n other=9,\n /\n", "ra_lw_physics", "37", "physics"),
    "empty_multiline_rhs": ("&physics\n ra_lw_physics =\n 4,\n /\n", "ra_lw_physics", "37", "physics"),
    "quoted_comment_like_token": ("&physics\n some_text='ra_lw_physics=4, ! not target',\n ra_lw_physics=4,\n /\n", "ra_lw_physics", "37", "physics"),
    "actual_duplicate": ("&physics\n ra_lw_physics=4,\n ra_lw_physics=5,\n /\n", "ra_lw_physics", "37", "physics"),
}
results = {}
for name, (text, key, value, group) in cases.items():
    try:
        after = set_assignment(text, key, value, group=group)
        results[name] = {"outcome": "returned", "before": text, "after": after}
    except Exception as error:
        results[name] = {"outcome": "rejected", "error": str(error), "before": text}
print(json.dumps({"source": str(source),
                  "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                  "cases": results}, indent=2))
