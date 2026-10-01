# Analysis 1 - reference export joint samples converted to encoder counts

export: TakeOne-main/runtime/reference-export.json  schema=take-one.export.v2  generated_at_utc=2026-09-12T02:41:36Z
robot_model hash in export: 444db0d4ff8b0b96c863ecbcea87fcd470526ab868e18028428d826312d9f284
mapping: packages/takeone/calibration.py ArmMapping (nominal midpoint; degrees = deg(q)*sign + zero_offset; count = degrees*4095/360 + mid)
cam arm -> phone calibration (arm_5B14111456); light arm -> light calibration (arm_5A7A058801)
CONDITIONAL on servo_to_urdf_transform_verified == false (configs/reference/previs_rig.json) and derived/*.json verified == false.

## A. rig_tall.xml joint range vs calibration-derived operating range (degrees, model frame)

| arm | joint | XML lo | XML hi | calib lo | calib hi | margin lo | margin hi | XML exceeds calib (deg lo/hi) | XML exceeds margin (deg lo/hi) |
|---|---|---|---|---|---|---|---|---|---|
| cam | shoulder_pan | -110.00 | 110.00 | -119.69 | 119.69 | -117.69 | 117.69 | 0.00 / 0.00 | 0.00 / 0.00 |
| cam | shoulder_lift | -100.00 | 100.00 | -103.21 | 103.21 | -101.21 | 101.21 | 0.00 / 0.00 | 0.00 / 0.00 |
| cam | elbow_flex | -96.83 | 96.83 | -96.84 | 97.36 | -94.84 | 95.36 | 0.00 / 0.00 | 1.99 / 1.47 |
| cam | wrist_flex | -95.00 | 95.00 | -101.67 | 101.67 | -99.67 | 99.67 | 0.00 / 0.00 | 0.00 / 0.00 |
| cam | wrist_roll | -157.21 | 162.79 | -180.00 | 180.00 | -178.00 | 178.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| light | shoulder_pan | -110.00 | 110.00 | -119.69 | 119.69 | -117.69 | 117.69 | 0.00 / 0.00 | 0.00 / 0.00 |
| light | shoulder_lift | -100.00 | 100.00 | -106.59 | 106.59 | -104.59 | 104.59 | 0.00 / 0.00 | 0.00 / 0.00 |
| light | elbow_flex | -96.83 | 96.83 | -97.32 | 97.49 | -95.32 | 95.49 | 0.00 / 0.00 | 1.51 / 1.34 |
| light | wrist_flex | -95.00 | 95.00 | -102.37 | 102.37 | -100.37 | 100.37 | 0.00 / 0.00 | 0.00 / 0.00 |
| light | wrist_roll | -157.21 | 162.79 | -180.00 | 180.00 | -178.00 | 178.00 | 0.00 / 0.00 | 0.00 / 0.00 |

Positive 'exceeds' values are degrees of XML-permitted travel the calibrated (or margin-reduced) range does not contain.
Zero means the XML range is inside the calibrated range on that side.

## B. Every joint sample in the export, converted to counts

joint_names: ['base_x', 'base_y', 'base_yaw', 'cam_shoulder_pan', 'cam_shoulder_lift', 'cam_elbow_flex', 'cam_wrist_flex', 'cam_wrist_roll', 'light_shoulder_pan', 'light_shoulder_lift', 'light_elbow_flex', 'light_wrist_flex', 'light_wrist_roll']

take samples: 117 (uniform 5 Hz grid in export); transition samples: 533 (decimated q_samples)

### take seg_f150301c Shot 1 · static

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 13 | 0.00 | 0.00 | 2120.5 | 2120.5 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 13 | -64.15 | -64.15 | 1257.3 | 1257.3 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 13 | 45.37 | 45.37 | 2500.6 | 2500.6 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 13 | 16.27 | 16.27 | 2203.6 | 2203.6 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 13 | -59.75 | -59.75 | 1367.8 | 1367.8 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 13 | 7.78 | 7.78 | 2207.9 | 2207.9 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 13 | 56.81 | 56.81 | 2631.7 | 2631.7 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 13 | 5.58 | 5.58 | 2052.5 | 2052.5 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 13 | -71.37 | -71.37 | 1227.7 | 1227.7 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 13 | 26.84 | 26.84 | 2352.8 | 2352.8 | [0, 4095] | 0 | 0 |

### ALL

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 650 | -11.49 | 91.64 | 1989.8 | 3162.9 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 650 | -99.40 | 99.40 | 856.3 | 3117.7 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 650 | -20.78 | 45.66 | 1748.1 | 2503.9 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 650 | -94.40 | 16.28 | 944.7 | 2203.7 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 650 | -156.61 | 162.19 | 266.1 | 3892.4 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 650 | -94.82 | 7.78 | 1041.0 | 2207.9 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 650 | -99.40 | 99.40 | 854.8 | 3116.2 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 650 | -91.05 | 5.58 | 953.3 | 2052.5 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 650 | -72.01 | 19.42 | 1220.3 | 2260.4 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 650 | -101.02 | 26.84 | 898.5 | 2352.8 | [0, 4095] | 0 | 0 |

### take seg_99ab7e7d Shot 2 · orbit

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 13 | 87.31 | 91.64 | 3113.6 | 3162.9 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 13 | -99.40 | -99.40 | 856.3 | 856.3 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 13 | 2.06 | 3.20 | 2007.9 | 2020.9 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 13 | -81.31 | -80.15 | 1093.6 | 1106.8 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 13 | 162.19 | 162.19 | 3892.4 | 3892.4 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 13 | -94.82 | -89.99 | 1041.0 | 1095.9 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 13 | 92.38 | 99.40 | 3036.3 | 3116.2 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 13 | -66.36 | -52.24 | 1234.1 | 1394.8 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 13 | -50.27 | -43.22 | 1467.6 | 1547.8 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 13 | -97.63 | -95.61 | 937.0 | 959.9 | [0, 4095] | 0 | 0 |

### take seg_aee1eb83 Shot 3 · static

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 13 | 0.01 | 0.01 | 2120.7 | 2120.7 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 13 | -64.39 | -64.39 | 1254.6 | 1254.6 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 13 | 45.66 | 45.66 | 2503.9 | 2503.9 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 13 | 16.22 | 16.22 | 2203.0 | 2203.0 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 13 | -57.73 | -57.73 | 1390.8 | 1390.8 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 13 | 7.74 | 7.74 | 2207.6 | 2207.6 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 13 | 65.91 | 65.91 | 2735.2 | 2735.2 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 13 | -2.90 | -2.90 | 1956.0 | 1956.0 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 13 | -71.99 | -71.99 | 1220.6 | 1220.6 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 13 | 8.00 | 8.00 | 2138.5 | 2138.5 | [0, 4095] | 0 | 0 |

### take seg_a0af5031 Shot 4 · tilt

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 13 | -11.49 | 0.00 | 1989.8 | 2120.5 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 13 | 99.40 | 99.40 | 3117.7 | 3117.7 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 13 | -20.78 | -13.76 | 1748.1 | 1828.0 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 13 | -94.40 | -94.40 | 944.7 | 944.7 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 13 | -156.61 | 162.19 | 266.1 | 3892.4 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 13 | 6.26 | 6.26 | 2190.7 | 2190.7 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 13 | 73.69 | 74.11 | 2823.8 | 2828.5 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 13 | -11.51 | -11.00 | 1858.1 | 1863.8 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 13 | -70.18 | -70.10 | 1241.2 | 1242.1 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 13 | -3.42 | -2.61 | 2008.6 | 2017.8 | [0, 4095] | 0 | 0 |

### take seg_63479e6f Shot 5 · static

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 13 | -0.01 | -0.01 | 2120.4 | 2120.4 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 13 | -63.59 | -63.59 | 1263.7 | 1263.7 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 13 | 45.22 | 45.22 | 2498.9 | 2498.9 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 13 | 15.86 | 15.86 | 2198.9 | 2198.9 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 13 | -61.72 | -61.72 | 1345.4 | 1345.4 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 13 | 7.77 | 7.77 | 2207.9 | 2207.9 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 13 | 61.00 | 61.00 | 2679.4 | 2679.4 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 13 | 1.99 | 1.99 | 2011.7 | 2011.7 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 13 | -71.98 | -71.98 | 1220.8 | 1220.8 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 13 | 18.17 | 18.17 | 2254.1 | 2254.1 | [0, 4095] | 0 | 0 |

### take seg_072884c6 Shot 6 · pan

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 13 | 0.00 | 14.87 | 2120.5 | 2289.7 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 13 | 99.40 | 99.40 | 3117.7 | 3117.7 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 13 | -16.92 | -1.32 | 1792.1 | 1969.5 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 13 | -94.40 | -94.40 | 944.7 | 944.7 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 13 | 46.26 | 118.87 | 2573.7 | 3399.6 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 13 | 5.67 | 5.68 | 2184.0 | 2184.1 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 13 | 77.77 | 78.52 | 2870.1 | 2878.7 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 13 | -16.54 | -15.58 | 1800.8 | 1811.8 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 13 | -69.08 | -68.87 | 1253.7 | 1256.1 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 13 | -10.45 | -9.04 | 1928.6 | 1944.7 | [0, 4095] | 0 | 0 |

### take seg_55699637 Shot 8 · static

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 13 | 0.01 | 0.01 | 2120.6 | 2120.6 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 13 | -63.62 | -63.62 | 1263.4 | 1263.4 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 13 | 45.26 | 45.26 | 2499.3 | 2499.3 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 13 | 15.85 | 15.85 | 2198.7 | 2198.7 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 13 | -59.17 | -59.17 | 1374.4 | 1374.4 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 13 | 7.77 | 7.77 | 2207.8 | 2207.8 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 13 | 61.63 | 61.63 | 2686.6 | 2686.6 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 13 | 1.39 | 1.39 | 2004.9 | 2004.9 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 13 | -72.01 | -72.01 | 1220.3 | 1220.3 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 13 | 16.84 | 16.84 | 2239.1 | 2239.1 | [0, 4095] | 0 | 0 |

### take seg_fef1cf6b Shot 9 · pull_back

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 13 | -1.77 | -0.02 | 2100.3 | 2120.3 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 13 | -99.40 | -99.40 | 856.3 | 856.3 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 13 | -16.06 | -15.49 | 1801.8 | 1808.4 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 13 | -63.02 | -62.04 | 1301.7 | 1312.8 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 13 | 109.82 | 117.78 | 3296.8 | 3387.2 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 13 | -5.08 | -5.08 | 2061.7 | 2061.7 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 13 | -99.40 | -99.40 | 854.8 | 854.8 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 13 | -91.05 | -91.05 | 953.3 | 953.3 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 13 | 19.42 | 19.42 | 2260.4 | 2260.4 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 13 | -101.02 | -101.02 | 898.5 | 898.5 | [0, 4095] | 0 | 0 |

### take seg_37cdb776 Shot 11 · static

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 13 | 0.01 | 0.01 | 2120.6 | 2120.6 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 13 | -64.38 | -64.38 | 1254.7 | 1254.7 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 13 | 45.59 | 45.59 | 2503.1 | 2503.1 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 13 | 16.28 | 16.28 | 2203.7 | 2203.7 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 13 | -58.38 | -58.38 | 1383.4 | 1383.4 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 13 | 7.76 | 7.76 | 2207.7 | 2207.7 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 13 | 63.11 | 63.11 | 2703.4 | 2703.4 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 13 | -0.25 | -0.25 | 1986.1 | 1986.1 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 13 | -71.84 | -71.84 | 1222.4 | 1222.4 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 13 | 13.14 | 13.14 | 2196.9 | 2196.9 | [0, 4095] | 0 | 0 |

### transition seg_f150301c->seg_99ab7e7d rotate

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 49 | 0.00 | 91.64 | 2120.5 | 3162.9 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 49 | -99.40 | -64.15 | 856.3 | 1257.3 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 49 | 3.20 | 45.37 | 2020.9 | 2500.6 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 49 | -81.31 | 16.27 | 1093.6 | 2203.6 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 49 | -59.75 | 162.19 | 1367.8 | 3892.4 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 49 | -89.99 | 7.78 | 1095.9 | 2207.9 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 49 | 56.81 | 92.38 | 2631.7 | 3036.3 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 49 | -52.24 | 5.58 | 1394.8 | 2052.5 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 49 | -71.37 | -50.27 | 1227.7 | 1467.6 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 49 | -95.61 | 26.84 | 959.9 | 2352.8 | [0, 4095] | 0 | 0 |

### transition seg_f150301c->seg_99ab7e7d drive

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 22 | 68.87 | 81.13 | 2903.9 | 3043.4 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 22 | -95.36 | -90.64 | 902.3 | 955.9 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 22 | 8.04 | 13.68 | 2075.9 | 2140.1 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 22 | -70.12 | -57.07 | 1220.9 | 1369.3 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 22 | 107.06 | 136.74 | 3265.3 | 3603.0 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 22 | -78.78 | -65.70 | 1223.4 | 1372.1 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 22 | 83.54 | 88.30 | 2935.8 | 2989.9 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 22 | -45.61 | -37.88 | 1470.2 | 1558.2 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 22 | -55.51 | -52.69 | 1408.0 | 1440.1 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 22 | -81.57 | -65.19 | 1119.6 | 1305.9 | [0, 4095] | 0 | 0 |

### transition seg_99ab7e7d->seg_aee1eb83 rotate

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 34 | 1.12 | 87.31 | 2133.2 | 3113.6 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 34 | -99.40 | -64.83 | 856.3 | 1249.6 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 34 | 2.06 | 45.11 | 2007.9 | 2497.6 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 34 | -80.15 | 15.00 | 1106.8 | 2189.1 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 34 | -54.95 | 162.19 | 1422.5 | 3892.4 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 34 | -94.82 | 6.44 | 1041.0 | 2192.8 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 34 | 66.33 | 99.40 | 2740.0 | 3116.2 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 34 | -66.36 | -3.70 | 1234.1 | 1946.9 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 34 | -71.63 | -43.22 | 1224.7 | 1547.8 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 34 | -97.63 | 6.66 | 937.0 | 2123.3 | [0, 4095] | 0 | 0 |

### transition seg_99ab7e7d->seg_aee1eb83 drive

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 26 | 41.45 | 82.89 | 2592.0 | 3063.3 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 26 | -97.63 | -81.01 | 876.5 | 1065.6 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 26 | 4.26 | 24.96 | 2033.0 | 2268.4 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 26 | -75.27 | -29.53 | 1162.3 | 1682.6 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 26 | 46.66 | 151.05 | 2578.3 | 3765.7 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 26 | -89.62 | -40.94 | 1100.0 | 1653.8 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 26 | 81.81 | 97.70 | 2916.0 | 3096.9 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 26 | -63.15 | -33.03 | 1270.7 | 1613.3 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 26 | -58.34 | -44.68 | 1375.9 | 1531.3 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 26 | -92.28 | -42.14 | 997.8 | 1568.2 | [0, 4095] | 0 | 0 |

### transition seg_aee1eb83->seg_a0af5031 drive

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 27 | 0.00 | 0.01 | 2120.5 | 2120.7 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 27 | -64.39 | 97.33 | 1254.6 | 3094.1 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 27 | -16.72 | 45.66 | 1794.3 | 2503.9 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 27 | -93.00 | 16.22 | 960.6 | 2203.0 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 27 | -57.73 | 116.63 | 1390.8 | 3374.2 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 27 | 6.28 | 7.74 | 2190.9 | 2207.6 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 27 | 65.91 | 73.59 | 2735.2 | 2822.6 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 27 | -10.90 | -2.90 | 1865.0 | 1956.0 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 27 | -71.99 | -70.21 | 1220.6 | 1240.9 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 27 | -2.47 | 8.00 | 2019.4 | 2138.5 | [0, 4095] | 0 | 0 |

### transition seg_a0af5031->seg_63479e6f drive

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 27 | -11.49 | -0.08 | 1989.8 | 2119.6 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 27 | -62.55 | 99.40 | 1275.5 | 3117.7 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 27 | -13.76 | 44.85 | 1828.0 | 2494.6 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 27 | -94.40 | 15.16 | 944.7 | 2190.9 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 27 | -156.61 | -62.33 | 266.1 | 1338.5 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 27 | 6.26 | 7.76 | 2190.7 | 2207.7 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 27 | 61.08 | 74.11 | 2680.3 | 2828.5 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 27 | -11.51 | 1.91 | 1858.1 | 2010.7 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 27 | -71.97 | -70.10 | 1220.9 | 1242.1 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 27 | -3.42 | 18.03 | 2008.6 | 2252.6 | [0, 4095] | 0 | 0 |

### transition seg_63479e6f->seg_072884c6 rotate

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 61 | -0.01 | 0.00 | 2120.4 | 2120.5 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 61 | -63.59 | 99.40 | 1263.7 | 3117.7 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 61 | -16.37 | 45.22 | 1798.3 | 2498.9 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 61 | -94.40 | 15.86 | 944.7 | 2198.9 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 61 | -61.72 | 118.87 | 1345.4 | 3399.6 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 61 | 5.68 | 7.77 | 2184.1 | 2207.9 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 61 | 61.00 | 77.77 | 2679.4 | 2870.1 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 61 | -15.58 | 1.99 | 1811.8 | 2011.7 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 61 | -71.98 | -69.08 | 1220.8 | 1253.7 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 61 | -9.04 | 18.17 | 1944.7 | 2254.1 | [0, 4095] | 0 | 0 |

### transition seg_63479e6f->seg_072884c6 drive

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 25 | -0.00 | -0.00 | 2120.5 | 2120.5 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 25 | -13.04 | 61.23 | 1838.6 | 2683.5 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 25 | -1.95 | 26.12 | 1962.3 | 2281.6 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 25 | -68.58 | -18.34 | 1238.4 | 1809.9 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 25 | -5.72 | 76.58 | 1982.5 | 2918.6 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 25 | 6.17 | 7.12 | 2189.6 | 2200.5 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 25 | 66.20 | 73.84 | 2738.5 | 2825.4 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 25 | -11.46 | -3.46 | 1858.6 | 1949.7 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 25 | -71.08 | -69.76 | 1231.0 | 1246.0 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 25 | -2.67 | 9.73 | 2017.1 | 2158.2 | [0, 4095] | 0 | 0 |

### transition seg_072884c6->seg_55699637 rotate

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 61 | 0.10 | 14.87 | 2121.6 | 2289.7 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 61 | -62.58 | 99.40 | 1275.2 | 3117.7 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 61 | -1.32 | 44.96 | 1969.5 | 2496.0 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 61 | -94.40 | 15.14 | 944.7 | 2190.8 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 61 | -58.50 | 46.26 | 1382.0 | 2573.7 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 61 | 5.67 | 7.75 | 2184.0 | 2207.7 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 61 | 61.74 | 78.52 | 2687.8 | 2878.7 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 61 | -16.54 | 1.28 | 1800.8 | 2003.6 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 61 | -71.99 | -68.87 | 1220.6 | 1256.1 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 61 | -10.45 | 16.67 | 1928.6 | 2237.1 | [0, 4095] | 0 | 0 |

### transition seg_072884c6->seg_55699637 drive

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 37 | 4.74 | 11.56 | 2174.4 | 2252.0 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 37 | -11.70 | 63.06 | 1853.9 | 2704.3 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 37 | 9.07 | 30.43 | 2087.6 | 2330.6 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 37 | -69.82 | -19.26 | 1224.3 | 1799.4 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 37 | -25.60 | 22.76 | 1756.3 | 2306.3 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 37 | 6.14 | 7.10 | 2189.3 | 2200.2 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 37 | 67.01 | 74.76 | 2747.8 | 2835.8 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 37 | -12.54 | -4.32 | 1846.3 | 1939.9 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 37 | -71.01 | -69.57 | 1231.7 | 1248.1 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 37 | -4.37 | 8.15 | 1997.8 | 2140.2 | [0, 4095] | 0 | 0 |

### transition seg_55699637->seg_fef1cf6b rotate

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 74 | -0.02 | 0.01 | 2120.3 | 2120.6 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 74 | -99.40 | -63.62 | 856.3 | 1263.4 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 74 | -16.06 | 45.26 | 1801.8 | 2499.3 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 74 | -62.04 | 15.85 | 1312.8 | 2198.7 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 74 | -59.17 | 116.53 | 1374.4 | 3373.0 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 74 | -5.08 | 7.77 | 2061.7 | 2207.8 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 74 | -99.40 | 61.63 | 854.8 | 2686.6 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 74 | -91.05 | 1.39 | 953.3 | 2004.9 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 74 | -72.01 | 19.42 | 1220.3 | 2260.4 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 74 | -101.02 | 16.84 | 898.5 | 2239.1 | [0, 4095] | 0 | 0 |

### transition seg_55699637->seg_fef1cf6b drive

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 14 | -0.01 | -0.00 | 2120.4 | 2120.5 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 14 | -82.99 | -80.03 | 1043.0 | 1076.7 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 14 | 12.06 | 17.14 | 2121.7 | 2179.4 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 14 | -26.32 | -19.87 | 1719.1 | 1792.4 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 14 | 21.40 | 35.95 | 2291.0 | 2456.4 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 14 | 0.81 | 1.87 | 2128.7 | 2140.8 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 14 | -25.55 | -12.22 | 1694.9 | 1846.5 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 14 | -48.66 | -41.00 | 1435.5 | 1522.6 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 14 | -30.08 | -22.51 | 1697.3 | 1783.5 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 14 | -46.96 | -37.21 | 1513.3 | 1624.3 | [0, 4095] | 0 | 0 |

### transition seg_fef1cf6b->seg_37cdb776 rotate

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 52 | -1.77 | -0.00 | 2100.3 | 2120.5 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 52 | -99.40 | -64.60 | 856.3 | 1252.2 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 52 | -15.49 | 45.21 | 1808.4 | 2498.7 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 52 | -63.02 | 15.78 | 1301.7 | 2198.0 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 52 | -57.32 | 109.82 | 1395.5 | 3296.8 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 52 | -5.08 | 7.68 | 2061.7 | 2206.8 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 52 | -99.40 | 62.08 | 854.8 | 2691.7 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 52 | -91.05 | -0.83 | 953.3 | 1979.6 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 52 | -71.26 | 19.42 | 1228.9 | 2260.4 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 52 | -101.02 | 12.42 | 898.5 | 2188.7 | [0, 4095] | 0 | 0 |

### transition seg_fef1cf6b->seg_37cdb776 drive

| joint | samples | q min (deg) | q max (deg) | count min | count max | calib range | out of calib | out of 2 deg margin |
|---|---|---|---|---|---|---|---|---|
| cam_shoulder_pan | 24 | -1.52 | -1.26 | 2103.2 | 2106.1 | [759, 3482] | 0 | 0 |
| cam_shoulder_lift | 24 | -94.52 | -89.43 | 911.8 | 969.8 | [813, 3161] | 0 | 0 |
| cam_elbow_flex | 24 | -6.98 | 1.91 | 1905.1 | 2006.2 | [883, 3092] | 0 | 0 |
| cam_wrist_flex | 24 | -51.98 | -40.43 | 1427.3 | 1558.6 | [862, 3175] | 0 | 0 |
| cam_wrist_roll | 24 | 61.92 | 86.40 | 2751.8 | 3030.3 | [0, 4095] | 0 | 0 |
| light_shoulder_pan | 24 | -3.30 | -1.43 | 2082.0 | 2103.3 | [758, 3481] | 0 | 0 |
| light_shoulder_lift | 24 | -76.77 | -53.12 | 1112.2 | 1381.3 | [773, 3198] | 0 | 0 |
| light_elbow_flex | 24 | -78.41 | -65.19 | 1097.1 | 1247.4 | [882, 3098] | 0 | 0 |
| light_wrist_flex | 24 | -6.57 | 6.72 | 1964.8 | 2115.9 | [875, 3204] | 0 | 0 |
| light_wrist_roll | 24 | -85.12 | -68.50 | 1079.3 | 1268.3 | [0, 4095] | 0 | 0 |

## C. Take status recorded in the export (for cross-reference)

| segment | label | status | checks fail | checks unknown | checks conditional |
|---|---|---|---|---|---|
| seg_f150301c | Shot 1 · static | fail | 0 | 0 | 1 |
| seg_99ab7e7d | Shot 2 · orbit | unknown | 0 | 0 | 1 |
| seg_aee1eb83 | Shot 3 · static | unknown | 0 | 0 | 1 |
| seg_a0af5031 | Shot 4 · tilt | fail | 4 | 0 | 1 |
| seg_63479e6f | Shot 5 · static | fail | 0 | 0 | 1 |
| seg_072884c6 | Shot 6 · pan | fail | 3 | 0 | 1 |
| seg_55699637 | Shot 8 · static | fail | 0 | 0 | 1 |
| seg_fef1cf6b | Shot 9 · pull_back | fail | 0 | 0 | 2 |
| seg_37cdb776 | Shot 11 · static | unknown | 0 | 0 | 1 |

## D. Export joint_limits_rad (what the planner solved inside) vs calibration bounds

| joint | export lo (deg) | export hi (deg) | calib margin lo | calib margin hi |
|---|---|---|---|---|
| cam_shoulder_pan | -110.00 | 110.00 | -117.69 | 117.69 |
| cam_shoulder_lift | -100.00 | 100.00 | -101.21 | 101.21 |
| cam_elbow_flex | -96.83 | 96.83 | -94.84 | 95.36 |
| cam_wrist_flex | -95.00 | 95.00 | -99.67 | 99.67 |
| cam_wrist_roll | -157.21 | 162.79 | -178.00 | 178.00 |
| light_shoulder_pan | -110.00 | 110.00 | -117.69 | 117.69 |
| light_shoulder_lift | -100.00 | 100.00 | -104.59 | 104.59 |
| light_elbow_flex | -96.83 | 96.83 | -95.32 | 95.49 |
| light_wrist_flex | -95.00 | 95.00 | -100.37 | 100.37 |
| light_wrist_roll | -157.21 | 162.79 | -178.00 | 178.00 |