#!/usr/bin/env python3
"""Compile and exercise the current WRF NetCDF backend; no WRF model.

MPI is optional and uses a monitor/backend/broadcast fixture, not module_io.
A fresh output directory is mandatory. Every child has a durable RC journal;
if storage fails after spawn, terminate/reap is attempted before propagation.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time
import uuid


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'sha256': digest, 'size_bytes': path.stat().st_size}


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def terminate_and_reap(process):
    errors = []
    # On an exceptional path, descendants may remain after their leader exits.
    # Signal the group regardless of the leader's poll state.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        except OSError as error:
            errors.append(repr(error))
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        except BaseException as error:
            errors.append(repr(error))
    return process.poll(), errors


class Runner:
    def __init__(self, output, timeout, environment, maximum):
        self.output = output
        self.timeout = timeout
        self.environment = environment
        self.maximum = maximum
        self.commands = []
        self.attempts = 0
        self.confirmed_children = 0

    def run(self, argv, cwd, kind, stdout_path=None):
        self.attempts += 1
        if self.attempts > self.maximum:
            raise RuntimeError('direct-child budget exceeded')
        number = self.attempts
        journal = self.output / f'command-{number:02d}.json'
        record = {'argv': [str(arg) for arg in argv], 'cwd': str(cwd), 'kind': kind,
                  'status': 'PREPARED', 'pid': None, 'actual_returncode': None,
                  'timed_out': False, 'started_at': time.time()}
        # A PREPARED persistence failure happens before launch.
        write_json(journal, record)
        process = None
        stdout_path = stdout_path or self.output / f'command-{number:02d}.stdout'
        stderr_path = self.output / f'command-{number:02d}.stderr'
        try:
            with stdout_path.open('xb') as out, stderr_path.open('xb') as err:
                try:
                    process = subprocess.Popen(record['argv'], cwd=cwd,
                                               env=self.environment, stdout=out,
                                               stderr=err, start_new_session=True)
                    self.confirmed_children += 1
                    record.update(pid=process.pid, status='STARTED')
                    write_json(journal, record)
                    returncode = process.wait(timeout=self.timeout)
                    record.update(actual_returncode=returncode, status='TERMINAL',
                                  finished_at=time.time())
                    # Actual RC precedes flush/hash/output interpretation.
                    write_json(journal, record)
                except BaseException as error:
                    record['exception'] = repr(error)
                    record['timed_out'] = isinstance(error, subprocess.TimeoutExpired)
                    if process is not None:
                        returncode, cleanup_errors = terminate_and_reap(process)
                        record.update(actual_returncode=returncode,
                                      status='REAP_PENDING' if returncode is None else 'TERMINAL_EXCEPTION',
                                      cleanup_errors=cleanup_errors, finished_at=time.time())
                    else:
                        record.update(status='OS_ERROR_START_UNCONFIRMED', child_start_state='UNKNOWN',
                                      finished_at=time.time())
                    try:
                        write_json(journal, record)
                    except BaseException as storage_error:
                        # No durable-record claim when filesystem persistence fails.
                        print('receipt persistence failed after cleanup:', repr(storage_error),
                              'in-memory terminal state:', json.dumps(record), file=sys.stderr)
                    self.commands.append(record)
                    raise
        except BaseException:
            raise
        self.commands.append(record)
        if returncode != 0:
            raise RuntimeError(f'{kind} actual RC {returncode}; receipt {journal}')
        return stdout_path


def tool(name):
    found = shutil.which(name)
    if found is None:
        raise ValueError(f'tool not found: {name}')
    return str(Path(found).absolute())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wrf_root', type=Path, help='WRF source directory')
    parser.add_argument('--workdir', type=Path, required=True, help='fresh directory; must not exist')
    parser.add_argument('--output', type=Path, required=True, help='new JSON receipt path, also saved as workdir/result.json')
    parser.add_argument('--fc', default='gfortran', help='compiler executable; MPI mode needs an MPI Fortran wrapper')
    parser.add_argument('--nf-config', default='nf-config')
    parser.add_argument('--cpp', default='cpp')
    parser.add_argument('--m4', default='m4')
    parser.add_argument('--mpiexec', help='optional MPI launcher executable')
    parser.add_argument('--mpi-ranks', type=int, default=4)
    parser.add_argument('--mpi-args', default='', help='additional launcher arguments, parsed with shlex')
    parser.add_argument('--mpi-interface', help='optional explicit MPICH_INTERFACE_HOSTNAME')
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    if not (0 < args.timeout <= 1200) or args.mpi_ranks < 2:
        parser.error('timeout must be finite in (0,1200]; MPI ranks must be >=2')
    wrf_root = args.wrf_root.resolve(strict=True)
    receipt = args.output.absolute()
    if receipt.exists() or receipt.is_symlink():
        parser.error('--output must not exist')
    output = args.workdir.absolute()
    output.mkdir(parents=True, exist_ok=False)
    backend = wrf_root / 'external/io_netcdf'
    ioapi = wrf_root / 'external/ioapi_share'
    def write_result(value):
        result = output / 'result.json'
        write_json(result, value)
        if receipt != result:
            receipt.parent.mkdir(parents=True, exist_ok=True)
            write_json(receipt, value)
    fixture = Path(__file__).with_suffix('.F90').resolve(strict=True)
    source_files = [backend / 'wrf_io.F90', backend / 'field_routines.F90', fixture,
                    ioapi / 'wrf_io_flags.h', ioapi / 'wrf_status_codes.h',
                    wrf_root / 'frame/module_io.F'] + sorted(backend.glob('*.code'))
    source_pins = [pin(path) for path in source_files]
    tools = {name: tool(getattr(args, name.replace('-', '_'))) for name in ('fc', 'nf-config', 'cpp', 'm4')}
    if args.mpiexec:
        tools['mpiexec'] = tool(args.mpiexec)
    environment = os.environ.copy()  # HOME and unrelated caller variables retained.
    if args.mpi_interface:
        environment['MPICH_INTERFACE_HOSTNAME'] = args.mpi_interface
    runner = Runner(output, args.timeout, environment, 10 if args.mpiexec else 8)
    plan = {'status': 'PREPARED', 'wrf_root': str(wrf_root), 'output_receipt': str(receipt), 'source_pins': source_pins,
            'tools': {key: pin(value) for key, value in tools.items()},
            'runner': pin(__file__), 'expected_direct_children': runner.maximum,
            'optimization_modes': ['O0', 'O2'], 'mpi_wrapper_enabled': bool(args.mpiexec),
            'mpi_ranks': args.mpi_ranks if args.mpiexec else 0,
            'scope': 'Actual ext_ncd backend; optional MPI monitor/API/broadcast wrapper, not WRF module_io',
            'wrf_builds': 0, 'wrf_forecasts': 0, 'rte_calls': 0, 'physical_acceptance': False}
    write_json(output / 'plan.json', plan)
    try:
        flags_log = runner.run([tools['nf-config'], '--fflags'], output, 'nf_config_flags')
        libs_log = runner.run([tools['nf-config'], '--flibs'], output, 'nf_config_libraries')
        flags = shlex.split(flags_log.read_text())
        libs = shlex.split(libs_log.read_text())
        library_dirs = [entry[2:] for entry in libs if entry.startswith('-L')]
        if library_dirs:
            environment['LD_LIBRARY_PATH'] = ':'.join(library_dirs + [environment.get('LD_LIBRARY_PATH', '')])
        dependency_files = []
        for entry in flags:
            if entry.startswith('-I'):
                candidate = Path(entry[2:]) / 'netcdf.inc'
                if candidate.is_file():
                    dependency_files.append(candidate)
        for name in ('netcdff', 'netcdf'):
            for directory in library_dirs:
                candidate = Path(directory) / ('lib' + name + '.so')
                if candidate.is_file():
                    dependency_files.append(candidate)
                    break
        dependency_pins = [pin(path) for path in dependency_files]
        write_json(output / 'toolchain.json', {'fflags': flags, 'flibs': libs,
                   'direct_netcdf_dependencies': dependency_pins,
                   'LD_LIBRARY_PATH': environment.get('LD_LIBRARY_PATH', ''),
                   'MPICH_INTERFACE_HOSTNAME': environment.get('MPICH_INTERFACE_HOSTNAME'),
                   'HOME_modified': False, 'full_loaded_runtime_closure_claimed': False})
        preprocessed = output / 'wrf_io.cpp.f90'
        expanded = output / 'wrf_io.f90'
        runner.run([tools['cpp'], '-P', '-traditional-cpp', '-DUSE_NETCDF4_FEATURES',
                    '-I' + str(ioapi), '-I' + str(backend), str(backend / 'wrf_io.F90')],
                   output, 'cpp', preprocessed)
        runner.run([tools['m4'], '-G', '-Uinclude', '-Uindex', '-Ulen', str(preprocessed)],
                   output, 'm4', expanded)
        # Execute the actual generic rank helper and its case conversion routine,
        # selected verbatim from module_io. This is not a full module_io runtime.
        helper_source = (wrf_root / 'frame/module_io.F').read_text()
        helper = output / 'generic_rank_helper.f90'
        selected = []
        for name in ('dim_from_memorder', 'lower_case'):
            pattern = rf'(?ims)^SUBROUTINE {name}\([^\n]*\).*?^END SUBROUTINE {name}\s*$'
            matches = re.findall(pattern, helper_source)
            if len(matches) != 1:
                raise RuntimeError(f'generic rank helper source roster changed: {name}')
            selected.append(matches[0])
        helper.write_text('\n'.join(selected) + '\n')
        results = []
        for optimization in ('O0', 'O2'):
            build = output / optimization
            build.mkdir()
            executable = build / 'fixture.exe'
            argv = [tools['fc'], '-' + optimization, '-g', '-fcheck=all', '-finit-integer=99', '-fallow-argument-mismatch',
                    '-ffree-form', '-ffree-line-length-none', '-cpp', '-I' + str(ioapi)]
            if args.mpiexec:
                argv += ['-DUSE_MPI']
            argv += flags + [str(expanded), str(backend / 'field_routines.F90'), str(helper), str(fixture)] + libs
            argv += ['-o', str(executable)]
            runner.run(argv, build, 'GNU_compile_link')
            executable_pin = pin(executable)
            for ranks in ([1, args.mpi_ranks] if args.mpiexec else [1]):
                case = build / f'ranks-{ranks}'
                case.mkdir()
                argv = [str(executable)] if ranks == 1 else [tools['mpiexec']] + shlex.split(args.mpi_args) + ['-n', str(ranks), str(executable)]
                log = runner.run(argv, case, 'fixture_serial' if ranks == 1 else 'fixture_MPI_wrapper')
                text = log.read_text()
                if (text.count('BACKEND_ROUNDTRIP_PASS') != 1 or text.count('REPLICA_PASS') != ranks
                        or text.count('HELPER_ORDER_CONTRACT_PASS') != 1):
                    raise RuntimeError('fixture success marker/replica roster mismatch')
                if pin(executable) != executable_pin:
                    raise RuntimeError('executable changed during fixture')
                results.append({'optimization': optimization, 'ranks': ranks,
                                'executable': executable_pin, 'netcdf': pin(case / 'zz.nc')})
        if [pin(item['path']) for item in source_pins] != source_pins:
            raise RuntimeError('source inputs changed during test')
        if [pin(item['path']) for item in dependency_pins] != dependency_pins:
            raise RuntimeError('direct NetCDF dependency changed during test')
        write_result({'status': 'PASS_SCOPED_NETCDF_ZZ_BACKEND',
                   'confirmed_direct_children': runner.confirmed_children, 'commands': runner.commands,
                   'results': results, 'source_pins': source_pins, 'direct_netcdf_dependencies': dependency_pins,
                   'mpi_is_actual_module_io': False, 'generic_rank_helper': pin(helper),
                   'generic_helper_executed': True, 'time_records': 2,
                   'time_unlimited_checked': True, 'real4_to_double_read_checked': True,
                   'invalid_read_order_checked': True,
                   'direct_helper_invalid_orders_checked': True,
                   'direct_helper_valid_order_count': 20,
                   'direct_helper_invalid_order_count': 5,
                   'direct_fieldio_invalid_read_checked': True,
                   'wrf_forecasts': 0, 'rte_calls': 0, 'physical_acceptance': False})
        print('PASS_SCOPED_NETCDF_ZZ_BACKEND', runner.confirmed_children)
    except BaseException as error:
        failure = {'status': 'FAIL_PRESERVED', 'confirmed_direct_children': runner.confirmed_children,
                   'commands': runner.commands, 'error': repr(error), 'physical_acceptance': False}
        try:
            write_result(failure)
        except BaseException as storage_error:
            print('final result persistence unavailable:', repr(storage_error), file=sys.stderr)
        raise


if __name__ == '__main__':
    main()
