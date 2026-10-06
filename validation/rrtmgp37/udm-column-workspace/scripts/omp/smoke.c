#include <omp.h>
#include <stdio.h>
int main(void){
 int bits=0;
 #pragma omp parallel reduction(|:bits)
 {bits|=1<<omp_get_thread_num();}
 printf("workers=%d bits=%d\n",omp_get_max_threads(),bits);
 return bits==3?0:1;
}
