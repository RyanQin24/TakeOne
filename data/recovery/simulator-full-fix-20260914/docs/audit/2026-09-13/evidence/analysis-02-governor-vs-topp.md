# Analysis 2 - governor bound vs per-axis time-optimal parameterisation

limits: {'arm_velocity_radps': 0.8, 'arm_acceleration_radps2': 1.8, 'arm_jerk_radps3': 12.0, 'cart_velocity_mps': 0.25, 'cart_acceleration_mps2': 0.35, 'cart_jerk_mps3': 1.5, 'yaw_velocity_radps': 0.6, 'yaw_acceleration_radps2': 1.2, 'yaw_jerk_radps3': 6.0, 'source': 'ASSUMED_placeholder'}
jerk ramp per reversal used for (d): 0.233 s (max over groups of a_lim/j_lim)

| kind | segment | nominal source s | governor duration s (a) | velocity-only s (b) | TOPP v+a s (c) | TOPP + jerk ramps s (d) | reversals | ratio a/c | ratio a/d |
|---|---|---|---|---|---|---|---|---|---|
| take | Shot 1 · static | 1.93 | 1.93 | 0.25 | 0.00 | 0.70 | 3 | n/a (locked-off, no motion) | n/a |
| take | Shot 2 · orbit | 2.57 | 9.95 | 6.41 | 7.13 | 10.16 | 13 | 1.4 | 1.0 |
| take | Shot 3 · static | 1.81 | 1.81 | 0.25 | 0.00 | 0.70 | 3 | n/a (locked-off, no motion) | n/a |
| take | Shot 4 · tilt | 2.69 | 20.33 | 10.54 | 11.55 | 13.65 | 9 | 1.8 | 1.5 |
| take | Shot 5 · static | 1.83 | 1.83 | 0.25 | 0.00 | 0.70 | 3 | n/a (locked-off, no motion) | n/a |
| take | Shot 6 · pan | 2.03 | 5.19 | 1.58 | 2.03 | 3.19 | 5 | 2.6 | 1.6 |
| take | Shot 8 · static | 1.89 | 1.89 | 0.25 | 0.00 | 0.70 | 3 | n/a (locked-off, no motion) | n/a |
| take | Shot 9 · pull_back | 1.76 | 5.83 | 2.00 | 2.71 | 3.41 | 3 | 2.1 | 1.7 |
| take | Shot 11 · static | 1.76 | 1.76 | 0.25 | 0.00 | 0.70 | 3 | n/a (locked-off, no motion) | n/a |
| reposition/rotate | seg_f150301c->seg_99ab7e7d | 0.00 | 35.98 | 3.64 | 4.02 | 10.78 | 29 | 9.0 | 3.3 |
| reposition/drive | seg_f150301c->seg_99ab7e7d | 0.00 | 4.04 | 1.55 | 2.27 | 2.97 | 3 | 1.8 | 1.4 |
| reposition/rotate | seg_f150301c->seg_99ab7e7d | 0.00 | 7.45 | 0.59 | 0.96 | 3.53 | 11 | 7.8 | 2.1 |
| reposition/rotate | seg_99ab7e7d->seg_aee1eb83 | 0.00 | 4.12 | 0.26 | 0.62 | 1.79 | 5 | 6.6 | 2.3 |
| reposition/drive | seg_99ab7e7d->seg_aee1eb83 | 0.00 | 8.23 | 5.15 | 5.86 | 6.56 | 3 | 1.4 | 1.3 |
| reposition/rotate | seg_99ab7e7d->seg_aee1eb83 | 0.00 | 24.82 | 2.25 | 2.61 | 8.91 | 27 | 9.5 | 2.8 |
| reposition/drive | seg_aee1eb83->seg_a0af5031 | 0.00 | 45.51 | 3.85 | 4.24 | 17.08 | 55 | 10.7 | 2.7 |
| reposition/drive | seg_a0af5031->seg_63479e6f | 0.00 | 37.52 | 3.56 | 4.00 | 26.63 | 97 | 9.4 | 1.4 |
| reposition/rotate | seg_63479e6f->seg_072884c6 | 0.00 | 15.26 | 1.22 | 1.71 | 6.15 | 19 | 8.9 | 2.5 |
| reposition/drive | seg_63479e6f->seg_072884c6 | 0.00 | 6.65 | 3.71 | 4.43 | 5.13 | 3 | 1.5 | 1.3 |
| reposition/rotate | seg_63479e6f->seg_072884c6 | 0.00 | 11.52 | 0.87 | 1.33 | 5.77 | 19 | 8.6 | 2.0 |
| reposition/rotate | seg_072884c6->seg_55699637 | 0.00 | 11.68 | 0.80 | 1.28 | 4.78 | 15 | 9.1 | 2.4 |
| reposition/drive | seg_072884c6->seg_55699637 | 0.00 | 6.68 | 3.75 | 4.46 | 5.16 | 3 | 1.5 | 1.3 |
| reposition/rotate | seg_072884c6->seg_55699637 | 0.00 | 15.63 | 1.11 | 1.63 | 6.06 | 19 | 9.6 | 2.6 |
| reposition/rotate | seg_55699637->seg_fef1cf6b | 0.00 | 25.65 | 2.63 | 2.99 | 10.23 | 31 | 8.6 | 2.5 |
| reposition/drive | seg_55699637->seg_fef1cf6b | 0.00 | 3.63 | 1.25 | 1.96 | 2.66 | 3 | 1.8 | 1.4 |
| reposition/rotate | seg_55699637->seg_fef1cf6b | 0.00 | 25.65 | 2.63 | 3.09 | 8.92 | 25 | 8.3 | 2.9 |
| reposition/rotate | seg_fef1cf6b->seg_37cdb776 | 0.00 | 9.45 | 0.88 | 1.32 | 4.82 | 15 | 7.1 | 2.0 |
| reposition/drive | seg_fef1cf6b->seg_37cdb776 | 0.00 | 4.99 | 2.30 | 3.01 | 3.71 | 3 | 1.7 | 1.3 |
| reposition/rotate | seg_fef1cf6b->seg_37cdb776 | 0.00 | 38.71 | 4.40 | 4.76 | 11.53 | 29 | 8.1 | 3.4 |

TOTAL physical rehearsal (takes floored at nominal source duration): governor 393.7 s; velocity-only 76.6 s; TOPP v+a 89.2 s; TOPP+jerk ramps 192.8 s
ratio governor / TOPP(v+a) = 4.41;  governor / TOPP+jerk = 2.04
source filmed duration 18.27 s; governor total is 21.5x the filmed source; TOPP+jerk total would be 10.6x

Caveats: (c) enforces velocity and acceleration per sample but not jerk; (d) adds one full jerk ramp per acceleration reversal, which over-counts
because ramps overlap with cruise. The true jerk-limited time-optimal duration lies between (c) and (a). The paths are identical to the
governor's (same PathSpline, same knots, same arclength parameterisation); only the time law differs. All limits are ASSUMED_placeholder.