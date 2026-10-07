#!/usr/bin/env python3
"""Generate and execute Registry subgrid metadata regression controls.

Consumes outputs from actual WRF Registry generators. It embeds the generated
logical assignment statements verbatim in a tiny Fortran sentinel program; it
also checks the generated allocation extents/dataset dimension names.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, os, re, shutil, signal, subprocess, time
from pathlib import Path

FIELDS = {
    "iseedarr_mult3d": (False, False, "ZZ", (False, False)),
    "zz_fixture": (False, False, "Z", (False, False)),
    "x_fixture": (True, False, "X", (True, False)),
    "y_fixture": (False, True, "Y", (False, True)),
    "xy_fixture": (False, False, "XY", (False, False)),
    "xy_subgrid_fixture": (True, True, "XY", (True, True)),
}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def extract(inc: Path, field: str):
    hits=[]
    for path in sorted(inc.glob("allocs_*.F")):
        lines=path.read_text(errors="replace").splitlines()
        for i,line in enumerate(lines):
            if re.search(rf"grid%tail_statevars%VarName\s*=\s*'{re.escape(field)}'",line,re.I):
                starts=[j for j in range(i) if "NULLIFY( grid%tail_statevars%next )" in lines[j]]
                if not starts: raise AssertionError(f"{path}: {field}: no linked-list node start")
                end=next((j for j in range(i+1,len(lines)) if re.fullmatch(r"\s*ENDIF\s*",lines[j],re.I)),None)
                if end is None: raise AssertionError(f"{path}: {field}: no metadata block end")
                start=starts[-1]
                block=lines[start:end+1]
                allocs=[x.strip() for x in lines[max(0,start-30):i] if re.search(rf"ALLOCATE\(\s*grid%{re.escape(field)}\(",x,re.I)]
                if not allocs:
                    # The actual allocate line may be farther away for long routines.
                    allocs=[x.strip() for x in lines[:i] if re.search(rf"ALLOCATE\(\s*grid%{re.escape(field)}\(",x,re.I)]
                subx=[x.strip() for x in block if re.search(r"grid%tail_statevars%subgrid_x\s*=",x,re.I)]
                suby=[x.strip() for x in block if re.search(r"grid%tail_statevars%subgrid_y\s*=",x,re.I)]
                names={k: re.findall(rf"grid%tail_statevars%{k}\s*=\s*'([^']*)'", "\n".join(lines[start:end+1]),re.I) for k in ("MemoryOrder","dimname1","dimname2","dimname3")}
                for key in ("Ndim", "Restart"):
                    names[key] = re.findall(rf"grid%tail_statevars%{key}\s*=\s*(\S+)", "\n".join(block), re.I)
                hits.append({"file":path,"line":start+1,"assign_x":subx,"assign_y":suby,"allocate":allocs[-1] if allocs else "","metadata":{k:(v[-1] if v else None) for k,v in names.items()}})
    if len(hits)!=1: raise AssertionError(f"{inc}: expected one generated metadata node for {field}, got {len(hits)}")
    return hits[0]

def generate_program(entries, output: Path):
    lines=["module sentinel_types", "implicit none", "type :: tail_t", " logical :: subgrid_x, subgrid_y", "end type", "type :: grid_t", " type(tail_t) :: tail_statevars", "end type", "contains"]
    for field,item in entries.items():
        lines += [f"subroutine check_{field}(ok)", " type(grid_t) :: grid", " logical, intent(out) :: ok", " ok=.true.", " grid%tail_statevars%subgrid_x=.true.", " grid%tail_statevars%subgrid_y=.true."]
        lines += [" ! Exact subgrid metadata statements extracted from the Registry-generated allocs file."]
        lines += item["assign_x"] + item["assign_y"]
        ex,ey,_,_=FIELDS[field]
        lines += [f" if (grid%tail_statevars%subgrid_x .neqv. .{ 'TRUE' if ex else 'FALSE' }.) ok=.false.", f" if (grid%tail_statevars%subgrid_y .neqv. .{ 'TRUE' if ey else 'FALSE' }.) ok=.false.", f" if (.not.ok) write(*,'(a)') 'SENTINEL_MISMATCH {field}'", f"end subroutine check_{field}"]
    lines += ["end module sentinel_types", "program sentinel_driver", "use sentinel_types", "implicit none", "logical :: ok, allok", "allok=.true."]
    for field in entries:
        lines += [f"call check_{field}(ok)", f"write(*,'(a,l1)') 'CASE {field} ',ok", "allok=allok.and.ok"]
    lines += ["if (.not.allok) stop 1", "end program sentinel_driver", ""]
    output.write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wrf_root", type=Path)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--fc", default="gfortran")
    args = parser.parse_args()
    wrf, work, output = args.wrf_root.resolve(), args.workdir.resolve(), args.output.resolve()
    if work.exists() or output.exists():
        parser.error("refusing to overwrite existing test artifacts")
    work.mkdir(parents=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt = {"schema": "registry-subgrid-metadata-v1", "status": "STARTING",
               "scope": "actual Registry generator plus source-selected metadata sentinel; no WRF forecast",
               "generator_source_sha256": sha(wrf / "tools/gen_allocs.c"), "children": [],
               "harness_sha256": sha(Path(__file__)),
               "model_invocations": 0, "physical_accepted": False}

    def save():
        temporary = output.with_name(output.name + ".tmp")
        temporary.write_text(json.dumps(receipt, indent=2) + "\n")
        temporary.replace(output)

    def run(argv, name, expected=0, timeout=180):
        log = work / (name + ".log")
        row = {"argv": argv, "name": name, "started": time.time()}
        receipt["children"].append(row)
        save()
        child = None
        with log.open("wb") as stream:
            try:
                child = subprocess.Popen(argv, cwd=work, stdout=stream,
                                         stderr=subprocess.STDOUT, start_new_session=True)
                row.update(pid=child.pid, status="RUNNING")
                save()
                row["returncode"] = child.wait(timeout=timeout)
            except BaseException:
                if child is not None:
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        row["returncode"] = child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        row["returncode"] = child.wait()
                    # The group may outlive its leader after a failed log write
                    # or timeout. Reap the leader above and stop any descendants.
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                raise
            finally:
                row.update(ended=time.time(), child_reaped=child is None or child.returncode is not None)
        row.update(status="TERMINAL", log_sha256=sha(log))
        save()
        if row["returncode"] != expected:
            raise RuntimeError(f"{name}: actual RC {row['returncode']}, expected {expected}; see {log}")
        return log.read_text()

    try:
        shutil.copytree(wrf / "tools", work / "tools",
                        ignore=shutil.ignore_patterns("*.o", "registry", "standard.exe"))
        (work / "Registry").mkdir()
        (work / "inc").mkdir()
        (work / "frame").mkdir()
        shutil.copyfile(wrf / "inc/streams.h", work / "inc/streams.h")
        dims = [line for line in (wrf / "Registry/registry.dimspec").read_text().splitlines()
                if re.match(r"^dimspec\s+(?:i\s+1|j\s+3|k\s+2)\s+standard_domain\s", line)
                or re.match(r"^dimspec\s+pertn3d\s", line)]
        rows = (wrf / "Registry/registry.stoch").read_text().splitlines()
        seed = [line for line in rows if re.match(r"^state\s+integer\s+ISEEDARR_mult3d\s", line)]
        config = [line for line in rows if re.match(r"^rconfig\s+integer\s+num_pert_3d\s", line)]
        if (len(dims), len(seed), len(config)) != (4, 1, 1):
            raise ValueError("source dimensions/seed/config roster changed")
        synthetic = [f'state integer {name} {dimensions} misc 1 - r "{name.upper()}" "manufactured metadata control" "1"'
                     for name, dimensions in (("zz_fixture", "k"), ("x_fixture", "*i"),
                         ("y_fixture", "*j"), ("xy_fixture", "ij"), ("xy_subgrid_fixture", "*i*j"))]
        registry = work / "Registry/Registry"
        registry.write_text("\n".join(dims + config + seed + synthetic) + "\n")
        receipt["registry_fixture_sha256"] = sha(registry)
        run(["make", "-C", "tools", "registry", "CC_TOOLS=" + args.cc,
             "CC_TOOLS_CFLAGS=-O0 -g -fcommon"], "registry-build")
        run([str(work / "tools/registry"), "-DEM_CORE=1", "-DNMM_CORE=0",
             "-DDA_CORE=0", "-DNMM_MAX_DIM=2600", "-DIWORDSIZE=4", "-DNEW_BDYS",
             "Registry/Registry"], "registry-generate", timeout=30)
        receipt["generator_executable_sha256"] = sha(work / "tools/registry")
        entries = {name: extract(work / "inc", name) for name in FIELDS}
        for field, (_, _, memory, axes) in FIELDS.items():
            item = entries[field]
            if not item["assign_x"] or not item["assign_y"]:
                raise ValueError(f"{field}: missing explicit subgrid metadata assignment")
            if item["metadata"]["MemoryOrder"] != memory:
                raise ValueError(f"{field}: memory order mismatch")
            if item["metadata"]["Ndim"] != str(len(memory)) or item["metadata"]["Restart"].upper() != ".TRUE.":
                raise ValueError(f"{field}: restart/array rank mismatch")
            allocation = item["allocate"].lower()
            if ("sr_x" in allocation, "sr_y" in allocation) != axes:
                raise ValueError(f"{field}: subgrid allocation extents mismatch")
            dimensions = {item["metadata"][f"dimname{i}"] for i in (1, 2, 3)}
            if ("west_east_subgrid" in dimensions, "south_north_subgrid" in dimensions) != axes:
                raise ValueError(f"{field}: subgrid dataset dimension mismatch")
        receipt["fields"] = {key: {name: value for name, value in item.items() if name != "file"}
                             for key, item in entries.items()}
        negative = copy.deepcopy(entries)
        negative["iseedarr_mult3d"]["assign_x"] = []
        negative["iseedarr_mult3d"]["assign_y"] = []
        receipt["negative_control"] = "manufactured omission of both seed-array assignments; not an upstream run"
        for label, items, expected in (("generated", entries, 0), ("omitted_seed_control", negative, 1)):
            source = work / (label + ".f90")
            executable = work / label
            generate_program(items, source)
            run([args.fc, "-O0", "-fcheck=all", "-o", str(executable), str(source)], label + "-compile")
            text = run([str(executable)], label + "-execute", expected=expected, timeout=20)
            failures = re.findall(r"SENTINEL_MISMATCH (\w+)", text)
            if failures != ([] if expected == 0 else ["iseedarr_mult3d"]):
                raise ValueError(f"unexpected sentinel failures: {failures}")
        receipt["status"] = "PASS_SCOPED_GENERATED_METADATA"
    except BaseException as error:
        receipt.update(status="FAIL_PRESERVED", error=repr(error))
        save()
        raise
    save()
    print(json.dumps({"status": receipt["status"], "fields": len(FIELDS),
                      "actual_children": len(receipt["children"]), "model_invocations": 0}))


if __name__ == "__main__":
    main()
