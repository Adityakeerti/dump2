# Civic RL results: root-cause investigation policy

> **SIMULATED.** Synthetic 6x6-block city, planted causes, synthetic residents. Nothing here is a
> measurement of a real city. ± is a 95% normal-approximation interval over episodes.

- Config hash: `89082769c4bcb4ab`
- Held-out seeds: 300000 .. 300029 (training used seeds from `seed` upward; ranges do not overlap)
- Checkpoint: 1200 training episodes, 47751 gradient updates, algorithm `DoubleDQN-candidate-scoring`

Metrics: **identified** = share of planted causes that an inspection or repair confirmed within the episode; **fixed** = share removed; **ticks to identify** = ticks from onset to confirmation (1 tick = 6 h); **onset error** = |estimated − true| start tick of each identified cause (CUSUM change point, see diagnosis.py); **complaints** = all complaints in the episode (lower is better); **false repairs** = repairs on healthy assets; **symptom actions** = pothole patches and traffic marshals.

## Scenario: `water_main_leak`

| Policy | Identified | Fixed | Ticks to identify | Onset error (ticks) | Complaints | False repairs | Symptom actions | Inspections | Reward |
|---|---|---|---|---|---|---|---|---|---|
| rl | 1.000 | 1.000 | 1.53 ± 0.64 | 0.86 ± 0.83 | 422.23 ± 51.28 | 3.77 ± 1.13 | 9.00 ± 1.44 | 36.80 ± 1.81 | -49.97 ± 5.52 |
| tracer | 0.933 | 0.933 | 2.89 ± 1.47 | 1.21 ± 1.07 | 420.70 ± 101.48 | 0.03 ± 0.07 | 26.47 ± 1.23 | 52.60 ± 1.21 | -58.88 ± 10.93 |
| complaint_count | 0.767 | 0.767 | 8.91 ± 4.27 | 1.15 ± 1.20 | 542.73 ± 133.83 | 41.63 ± 2.68 | 50.53 ± 3.93 | 0.00 ± 0.00 | -108.71 ± 14.58 |
| random | 0.867 | 0.600 | 13.62 ± 3.87 | 0.72 ± 0.83 | 692.73 ± 103.81 | 31.37 ± 1.67 | 12.07 ± 1.13 | 31.10 ± 1.98 | -107.15 ± 11.18 |

## Scenario: `sewer_blockage`

| Policy | Identified | Fixed | Ticks to identify | Onset error (ticks) | Complaints | False repairs | Symptom actions | Inspections | Reward |
|---|---|---|---|---|---|---|---|---|---|
| rl | 1.000 | 1.000 | 3.37 ± 0.59 | 1.73 ± 0.69 | 424.50 ± 54.19 | 2.70 ± 1.46 | 8.87 ± 1.18 | 37.67 ± 1.75 | -49.30 ± 6.06 |
| tracer | 0.867 | 0.867 | 5.31 ± 1.86 | 1.56 ± 0.68 | 455.13 ± 98.27 | 0.10 ± 0.11 | 25.53 ± 1.07 | 53.60 ± 1.08 | -61.53 ± 10.01 |
| complaint_count | 0.867 | 0.867 | 6.00 ± 2.12 | 1.84 ± 0.95 | 427.23 ± 77.73 | 40.93 ± 2.68 | 53.63 ± 3.79 | 0.00 ± 0.00 | -95.29 ± 8.54 |
| random | 0.933 | 0.500 | 13.07 ± 3.50 | 2.39 ± 1.21 | 728.93 ± 90.25 | 30.50 ± 1.26 | 12.43 ± 1.05 | 31.93 ± 1.39 | -108.68 ± 9.03 |

## Scenario: `missed_waste_route`

| Policy | Identified | Fixed | Ticks to identify | Onset error (ticks) | Complaints | False repairs | Symptom actions | Inspections | Reward |
|---|---|---|---|---|---|---|---|---|---|
| rl | 1.000 | 1.000 | 0.03 ± 0.07 | 1.80 ± 1.11 | 406.03 ± 51.35 | 2.00 ± 1.30 | 8.40 ± 1.06 | 39.27 ± 1.90 | -46.66 ± 5.64 |
| tracer | 1.000 | 1.000 | 1.83 ± 1.11 | 1.50 ± 1.09 | 352.80 ± 22.52 | 0.03 ± 0.07 | 26.07 ± 1.24 | 52.93 ± 1.24 | -51.10 ± 2.29 |
| complaint_count | 1.000 | 1.000 | 2.83 ± 0.83 | 1.07 ± 0.83 | 372.67 ± 23.46 | 42.30 ± 2.78 | 55.07 ± 3.04 | 0.00 ± 0.00 | -89.76 ± 2.35 |
| random | 0.933 | 0.567 | 11.46 ± 3.31 | 1.14 ± 0.80 | 833.07 ± 70.63 | 31.43 ± 1.61 | 11.93 ± 1.17 | 31.20 ± 1.75 | -119.04 ± 7.04 |

## Scenario: `streetlight_feeder_fault`

| Policy | Identified | Fixed | Ticks to identify | Onset error (ticks) | Complaints | False repairs | Symptom actions | Inspections | Reward |
|---|---|---|---|---|---|---|---|---|---|
| rl | 1.000 | 1.000 | 0.03 ± 0.07 | 2.60 ± 1.20 | 406.93 ± 51.92 | 1.83 ± 1.40 | 8.10 ± 1.09 | 39.83 ± 1.91 | -46.68 ± 5.82 |
| tracer | 1.000 | 1.000 | 1.67 ± 0.81 | 2.20 ± 1.16 | 360.93 ± 22.97 | 0.03 ± 0.07 | 25.77 ± 1.30 | 53.23 ± 1.30 | -53.09 ± 2.73 |
| complaint_count | 1.000 | 1.000 | 3.63 ± 1.43 | 0.47 ± 0.35 | 396.73 ± 33.88 | 44.00 ± 2.59 | 54.90 ± 2.70 | 0.00 ± 0.00 | -93.98 ± 3.39 |
| random | 0.933 | 0.667 | 8.21 ± 2.85 | 1.21 ± 0.81 | 771.63 ± 79.00 | 31.90 ± 1.39 | 11.80 ± 1.08 | 30.63 ± 1.87 | -120.01 ± 9.71 |

## Scenario: `crime_hotspot`

| Policy | Identified | Fixed | Ticks to identify | Onset error (ticks) | Complaints | False repairs | Symptom actions | Inspections | Reward |
|---|---|---|---|---|---|---|---|---|---|
| rl | 1.000 | 1.000 | 1.73 ± 0.41 | 2.27 ± 1.22 | 434.93 ± 55.59 | 2.77 ± 1.15 | 8.33 ± 1.06 | 41.27 ± 1.80 | -51.83 ± 6.07 |
| tracer | 1.000 | 1.000 | 4.90 ± 1.84 | 1.27 ± 0.76 | 389.77 ± 46.48 | 0.07 ± 0.09 | 25.43 ± 1.27 | 53.57 ± 1.27 | -57.84 ± 5.84 |
| complaint_count | 0.867 | 0.867 | 4.46 ± 2.76 | 2.91 ± 1.41 | 363.33 ± 25.83 | 48.13 ± 3.73 | 52.17 ± 3.87 | 0.00 ± 0.00 | -94.61 ± 4.82 |
| random | 1.000 | 0.933 | 5.57 ± 1.86 | 1.70 ± 0.94 | 568.87 ± 51.33 | 31.13 ± 1.35 | 12.27 ± 0.99 | 30.67 ± 1.17 | -95.74 ± 5.87 |

## Scenario: `mixed`

| Policy | Identified | Fixed | Ticks to identify | Onset error (ticks) | Complaints | False repairs | Symptom actions | Inspections | Reward |
|---|---|---|---|---|---|---|---|---|---|
| rl | 1.000 | 1.000 | 1.46 ± 0.57 | 1.57 ± 0.68 | 424.27 ± 56.11 | 2.23 ± 0.98 | 8.27 ± 0.99 | 39.60 ± 1.58 | -45.18 ± 5.92 |
| tracer | 0.935 | 0.935 | 3.09 ± 1.09 | 1.85 ± 0.70 | 487.40 ± 111.83 | 0.10 ± 0.11 | 26.27 ± 1.49 | 52.17 ± 1.49 | -62.07 ± 11.95 |
| complaint_count | 0.761 | 0.761 | 5.77 ± 2.31 | 1.39 ± 0.80 | 668.80 ± 198.04 | 45.70 ± 3.11 | 46.27 ± 4.99 | 0.00 ± 0.00 | -120.59 ± 21.59 |
| random | 0.913 | 0.674 | 10.40 ± 2.48 | 1.25 ± 0.71 | 855.20 ± 92.63 | 31.73 ± 1.60 | 11.37 ± 1.27 | 30.70 ± 1.52 | -121.78 ± 9.77 |

## Scenario: `control`

| Policy | Identified | Fixed | Ticks to identify | Onset error (ticks) | Complaints | False repairs | Symptom actions | Inspections | Reward |
|---|---|---|---|---|---|---|---|---|---|
| rl | n/a | n/a | n/a | n/a | 393.70 ± 47.51 | 1.20 ± 0.93 | 8.80 ± 1.16 | 40.00 ± 1.62 | -52.88 ± 5.20 |
| tracer | n/a | n/a | n/a | n/a | 300.00 ± 13.82 | 0.03 ± 0.07 | 26.67 ± 1.25 | 53.07 ± 1.26 | -54.14 ± 1.62 |
| complaint_count | n/a | n/a | n/a | n/a | 318.60 ± 13.62 | 42.13 ± 2.17 | 59.20 ± 2.19 | 0.00 ± 0.00 | -92.61 ± 1.22 |
| random | n/a | n/a | n/a | n/a | 467.17 ± 36.06 | 31.33 ± 1.48 | 12.17 ± 1.26 | 31.43 ± 1.70 | -90.09 ± 4.25 |

## Paired difference: rl − tracer (same seeds)

An interval that excludes 0 is a difference at roughly the 95% level. Reward and identified: higher is better for rl. Complaints and false repairs: lower is better for rl.

| Scenario | Δ reward | Δ complaints | Δ identified causes / episode | Δ false repairs |
|---|---|---|---|---|
| water_main_leak | 8.91 ± 10.53 | 1.53 ± 99.18 | 0.07 ± 0.09 | 3.73 ± 1.13 |
| sewer_blockage | 12.23 ± 10.84 | -30.63 ± 102.94 | 0.13 ± 0.12 | 2.60 ± 1.47 |
| missed_waste_route | 4.44 ± 4.70 | 53.23 ± 43.56 | 0.00 ± 0.00 | 1.97 ± 1.30 |
| streetlight_feeder_fault | 6.41 ± 5.23 | 46.00 ± 47.04 | 0.00 ± 0.00 | 1.80 ± 1.40 |
| crime_hotspot | 6.01 ± 6.71 | 45.17 ± 57.19 | 0.00 ± 0.00 | 2.70 ± 1.15 |
| mixed | 16.88 ± 12.77 | -63.13 ± 120.87 | 0.10 ± 0.11 | 2.13 ± 0.98 |
| control | 1.26 ± 4.41 | 93.70 ± 41.92 | 0.00 ± 0.00 | 1.17 ± 0.94 |

## Paired difference: rl − complaint_count (same seeds)

An interval that excludes 0 is a difference at roughly the 95% level. Reward and identified: higher is better for rl. Complaints and false repairs: lower is better for rl.

| Scenario | Δ reward | Δ complaints | Δ identified causes / episode | Δ false repairs |
|---|---|---|---|---|
| water_main_leak | 58.74 ± 14.82 | -120.50 ± 135.65 | 0.23 ± 0.15 | -37.87 ± 3.15 |
| sewer_blockage | 45.99 ± 9.84 | -2.73 ± 82.94 | 0.13 ± 0.12 | -38.23 ± 3.68 |
| missed_waste_route | 43.10 ± 4.93 | 33.37 ± 38.59 | 0.00 ± 0.00 | -40.30 ± 3.38 |
| streetlight_feeder_fault | 47.30 ± 4.43 | 10.20 ± 34.27 | 0.00 ± 0.00 | -42.17 ± 3.47 |
| crime_hotspot | 42.78 ± 8.02 | 71.60 ± 53.19 | 0.13 ± 0.12 | -45.37 ± 4.33 |
| mixed | 75.41 ± 22.12 | -244.53 ± 203.96 | 0.37 ± 0.22 | -43.47 ± 3.19 |
| control | 39.73 ± 4.86 | 75.10 ± 39.77 | 0.00 ± 0.00 | -40.93 ± 2.59 |

## Training curve (blocks of 50 episodes)

| Episodes | Teacher-forced | Mean reward | Identified | Complaints |
|---|---|---|---|---|
| 1-50 | yes | -60.39 | 0.96 | 468.2 |
| 51-100 | yes | -56.4 | 0.973 | 425.1 |
| 101-150 | yes | -55.68 | 0.973 | 425.0 |
| 151-200 | no | -107.55 | 0.975 | 745.6 |
| 201-250 | no | -113.55 | 0.962 | 817.6 |
| 251-300 | no | -97.12 | 1.0 | 678.8 |
| 301-350 | no | -88.4 | 1.0 | 590.3 |
| 351-400 | no | -89.32 | 0.974 | 625.2 |
| 401-450 | no | -83.92 | 0.986 | 574.3 |
| 451-500 | no | -81.38 | 1.0 | 566.1 |
| 501-550 | no | -77.51 | 1.0 | 543.5 |
| 551-600 | no | -77.95 | 1.0 | 581.2 |
| 601-650 | no | -73.65 | 0.986 | 546.7 |
| 651-700 | no | -71.49 | 1.0 | 548.7 |
| 701-750 | no | -71.7 | 1.0 | 541.9 |
| 751-800 | no | -67.2 | 1.0 | 542.0 |
| 801-850 | no | -65.53 | 1.0 | 522.2 |
| 851-900 | no | -67.37 | 0.986 | 531.8 |
| 901-950 | no | -62.65 | 0.975 | 543.2 |
| 951-1000 | no | -63.03 | 0.962 | 563.0 |
| 1001-1050 | no | -54.1 | 1.0 | 488.7 |
| 1051-1100 | no | -57.92 | 1.0 | 541.2 |
| 1101-1150 | no | -55.18 | 1.0 | 508.1 |
| 1151-1200 | no | -53.65 | 1.0 | 473.2 |
