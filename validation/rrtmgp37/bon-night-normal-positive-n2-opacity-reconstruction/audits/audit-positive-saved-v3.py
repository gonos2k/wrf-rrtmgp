#!/usr/bin/env python3
"""Metadata-only correction for the frozen positive-N2 terminal audit v2.
Validates its report and inventory pins, then corrects one stale provenance note.
It does not reopen target values or recalculate any source/table terms.
"""
import hashlib,json,pathlib
ROOT=pathlib.Path.cwd()
V2=ROOT/"build/udm37-normal-positive-n2-opacity-terminal-audit-v2/terminal-audit.json"
INV=ROOT/"build/udm37-normal-positive-n2-production-inventory-v1/inventory.json"
REVIEW=ROOT/"build/udm37-normal-positive-n2-opacity-source-review-v1/review.json"
OUT=ROOT/"build/udm37-normal-positive-n2-opacity-terminal-audit-v3/terminal-audit.json"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(V2)=="da18208155aed69225369168a34bc0692e2a34a610ba6826ecc60583b928a760"
assert sha(INV)=="d870e6c9f1355186e0238c96e7c3926afe7bf21e1a97b1c0bf49b65240bd8ab2"
old=json.loads(V2.read_text()); inv=json.loads(INV.read_text()); review=json.loads(REVIEW.read_text())
assert review["reviewed_artifacts"]["production_inventory"]["sha256"]==sha(INV)
assert inv["status"]=="FOUND_AUTHENTICATED_NORMAL_POSITIVE_N2_ACTUAL_WRF_CAPTURE"
needle="The parent normal-carrier source-compatibility note remains applicable: build-receipt source-generation mismatch is disclosed in build/udm37-bon-night-normal-carrier-inventory-v3/source-compatibility.json."
assert old["provenance_limits"].count(needle)==1
new=json.loads(json.dumps(old))
new["provenance_limits"][new["provenance_limits"].index(needle)]=(
"This is the actual positive-N2 campaign capture for the selected 085618 source/build snapshot. "
"The authenticated production inventory (build/udm37-normal-positive-n2-production-inventory-v1/inventory.json) confirms byte identity "
"for the radiation adapter, gas constants, frontend, kernel, loader, and LW coefficient table against the current comparison worktree; "
"the separately instrumented trace module differs. The old absent-N2/direct-reference source-compatibility note does not apply to this "
"positive-N2 campaign point. This does not establish identity of the entire WRF source tree or a physical-accuracy result.")
assert OUT.exists() and json.loads(OUT.read_text())==new
assert all(new[k]==old[k] for k in old if k!="provenance_limits")
print(json.dumps({"status":"METADATA_ONLY_CORRECTION_VALIDATED","v2_report_sha256":sha(V2),"inventory_sha256":sha(INV),"v3_report_sha256":sha(OUT)},indent=2))
