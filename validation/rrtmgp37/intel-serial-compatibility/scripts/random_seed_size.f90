program seed_size
integer :: n
call random_seed(size=n)
print *, n
end program
