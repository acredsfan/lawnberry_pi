# Data Model — LawnBerry Pi v2

## Entities

### SensorData
- timestamp (ms)
- imu (quat, accel, gyro)
- power (ina3221: ch1 battery, ch3 solar)
- tof (left, right)
- env (temp, humidity, pressure)
- wheel (left_ticks, right_ticks)
- validity_flags

### NavigationState
- position (lat, lon, alt)
- heading, speed
- mode (auto, manual, paused, estop)
- gps_status (fix, rtk, lost)
- path_id, segment_index

### MotorCommand
- left_pwm, right_pwm
- blade_enabled
- safety_interlocks (bools)

### PowerReading
- battery_v, battery_a
- solar_v, solar_a
- soc_estimate

### Job
- id, name, status (queued, running, paused, done, failed)
- zone_id, started_at, eta

### Zone
- id, name, polygon, exclusions[]
- priority
- locations: home, am_sun, pm_sun (lat/lon)

### UserSession
- auth_state (MFA enforced)
- roles (operator)
- audit_log_refs[]

### Alert
- id, type (obstacle, tilt, power, network, gps)
- severity, message, ts

## Relationships
- Zone has many Jobs
- Jobs produce Alerts and update NavigationState
- SensorData feeds NavigationState
- PowerReading contributes to Alerts (low battery)

## Constraints
- INA3221 channels: 1=battery, 2=unused, 3=solar
- Single-owner camera device; IPC for frames
- GPS-loss policy: dead reckoning ≤2 min then stop
