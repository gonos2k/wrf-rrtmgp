/* Test-only x86-64 SSE2 ABI overrides; each vector lane calls scalar libc. */
#include <emmintrin.h>
#include <math.h>

__m128d _ZGVbN2v_log(__m128d x)
{
    double in[2], out[2];
    _mm_storeu_pd(in, x);
    out[0] = log(in[0]);
    out[1] = log(in[1]);
    return _mm_loadu_pd(out);
}

__m128d _ZGVbN2v_exp(__m128d x)
{
    double in[2], out[2];
    _mm_storeu_pd(in, x);
    out[0] = exp(in[0]);
    out[1] = exp(in[1]);
    return _mm_loadu_pd(out);
}
