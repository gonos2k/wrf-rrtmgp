program consumer
  use mo_rte_kind, only: wp
  use mo_gas_concentrations, only: ty_gas_concs
  implicit none
  type(ty_gas_concs) :: gases
  character(len=3), parameter :: names(2) = [character(len=3) :: 'h2o', 'co2']
  character(len=128) :: err
  if (wp /= kind(1.0d0)) error stop 'unexpected RRTMGP wp kind'
  err = gases%init(names)
  if (len_trim(err) /= 0) error stop 'gas concentration initialization failed'
  if (gases%get_num_gases() /= 2) error stop 'unexpected gas count'
  print *, 'INSTALLED_WRF_RRTMGP_CONSUMER_PASS', wp
end program consumer
