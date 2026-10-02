# CPU OpenMP backend

고정 RTE–RRTMGP의 OpenMP 지시문은 GPU `target`/device map을 포함한다. GNU 13.3의 일반 WRF smpar/dm+sm 빌드는 파생형의 allocatable member map을 컴파일하지 못했다. WRF CPU backend는 `RRTMGP_CPU_ONLY`로 해당 offload 지시문 그룹만 감싼다. 일반 Fortran 계산 본문과 host의 `-fopenmp`·`OMP SIMD` 지시문은 보존한다. Make/CMake 모두 CPU macro를 설정하고, Make 설정 fingerprint에는 macro가 포함되어 이전 object를 재사용하지 않는다.

333개 offload 지시문 그룹이 있는 13개 파일에서 guard를 제거하면 PR #9의 원문과 byte 동일하다. GPU backend 지원을 선언하지 않으며 향후 별도 구현/검증해야 한다. audit 환경의 첫 접근도 named OpenMP critical로 직렬화하여 공유 상태 초기화 경합을 막는다. serial capture/audit의 MPI·다중 스레드 제한은 유지한다.

동시 호출 시험은 library와 adapter 모두 OpenMP로 빌드한다. 계수와 상수는 직렬 초기화하고, 실제 1/2/4 스레드 팀에서 64개의 서로 다른 3층 기둥을 팀별 8회 실행한다. UDM rain/snow precipitation 경로와 고정 column seed를 사용하며 모든 LW/SW flux·heating·청천·직달/산란/분광 진단을 직렬 출력과 비교했다. 최대 차이는 정확히 0이었다. 기본 직렬 독립 시험 54개도 통과했다.

```sh
cmake -S WRF/test/rrtmgp -B build/cpu-openmp \
  -DRRTMGP_TEST_OPENMP=ON -DRRTMGP_DATA_DIR="$PWD/WRF/run"
cmake --build build/cpu-openmp --target test_rrtmgp_openmp --parallel 4
ctest --test-dir build/cpu-openmp -R cpu_openmp_reentrancy --output-on-failure -V
```

실제 GNU smpar SCM과 dm+sm `em_real` 빌드도 성공했다. 실제 WRF의 스레드/MPI 분할 결과, 계수 오류 collective 종료, restart 및 실예보 검증은 실행 결과를 별도로 기록하며 라이브러리 동시 호출 시험에서 추론하지 않는다.

CPU guard 적용 전후 GNU 직렬 SCM control/mixed의 37번 210개 및 4번 208개 history 배열과 파일 해시는 모두 동일했다. 실제 OpenMP의 마지막 source snapshot에 대한 비교 결과는 별도 receipt에 남긴다.
