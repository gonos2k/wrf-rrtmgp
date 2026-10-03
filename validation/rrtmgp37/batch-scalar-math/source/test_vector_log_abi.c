#include <emmintrin.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern __m128d _ZGVbN2v_log(__m128d x);
int main(int argc, char **argv)
{
    FILE *f; double x[2], got[2], ref[2]; uint64_t gb, rb; size_t n=0;
    if(argc!=2) return 2;
    f=fopen(argv[1],"rb"); if(!f){perror("fopen"); return 2;}
    while(fread(&x[0],sizeof(double),1,f)==1) {
        int have2=(fread(&x[1],sizeof(double),1,f)==1);
        if(!have2) x[1]=1.0;
        if(!(x[0]>0.0) || !(x[1]>0.0) || !isfinite(x[0]) || !isfinite(x[1])) return 3;
        __m128d y=_ZGVbN2v_log(_mm_loadu_pd(x));
        _mm_storeu_pd(got,y);
        ref[0]=log(x[0]); ref[1]=log(x[1]);
        memcpy(&gb,&got[0],sizeof gb); memcpy(&rb,&ref[0],sizeof rb);
        if(gb!=rb){fprintf(stderr,"lane0 mismatch #%zu: %a vs %a\n",n,got[0],ref[0]);return 4;}
        memcpy(&gb,&got[1],sizeof gb); memcpy(&rb,&ref[1],sizeof rb);
        if(gb!=rb){fprintf(stderr,"lane1 mismatch #%zu: %a vs %a\n",n,got[1],ref[1]);return 5;}
        n+=2;
        if(!have2) break;
    }
    fclose(f); printf("PASS exact scalar-libm bits for %zu lanes\n",n); return 0;
}
