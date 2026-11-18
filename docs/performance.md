# Performance measurement

Run `python scripts/benchmark.py` inside the development environment. The benchmark constructs 1,000 baseline observations and 1,000 candidate observations with one metric each. It performs one warmup, then seven repeats of 100 comparisons, and reports the median and minimum time per comparison.

On 2026-11-17, Python 3.15.2 on the development macOS host measured 0.859 ms median and 0.855 ms minimum per comparison. These are local synthetic measurements, not service guarantees or comparisons with other products. Hardware load, interpreter and data shape affect results.

Timing excludes fixture loading, construction, serialization, network access and cloud query execution. Input JSON is limited to 5 MB. Comparisons retain the observations in memory and sort by execution ID for deterministic calculation. Future collection must remain bounded. No claim is made that this is the fastest implementation.

Release-readiness rerun on the same macOS development host (2026-11-18):

| Python | Median ms/comparison | Minimum ms/comparison |
| --- | ---: | ---: |
| 3.15.2 | 0.870 | 0.853 |

Each result uses 1,000 observations per group and seven repeats of 100 comparisons after warmup. These timings exclude IO, report rendering and network activity.
