#ifndef MWRS_CONFIG_H
#define MWRS_CONFIG_H

/*
 * Hardware-owner configuration gate.
 *
 * The checked-in firmware is intentionally protocol-ready but actuator-locked.
 * Set all confirmation flags to 1 only after the STM32 owner has verified the
 * board wiring, emergency stop, driver firmware/protocol, wheel dimensions,
 * gearbox ratios, zero coordinates and direction signs on the real rover.
 */
#ifndef MWRS_ACTUATION_ENABLED
#define MWRS_ACTUATION_ENABLED               0
#endif
#ifndef MWRS_HARDWARE_ESTOP_CONFIGURED
#define MWRS_HARDWARE_ESTOP_CONFIGURED       0
#endif
#ifndef MWRS_DRIVER_PROTOCOLS_CONFIRMED
#define MWRS_DRIVER_PROTOCOLS_CONFIRMED       0
#endif
#ifndef MWRS_WHEEL_CALIBRATION_CONFIRMED
#define MWRS_WHEEL_CALIBRATION_CONFIRMED      0
#endif

#if MWRS_ACTUATION_ENABLED && !MWRS_HARDWARE_ESTOP_CONFIGURED
#error "Actuation requires a verified hardware emergency-stop input"
#endif
#if MWRS_ACTUATION_ENABLED && !MWRS_DRIVER_PROTOCOLS_CONFIRMED
#error "Actuation requires verified MKS SERVO57D and BLD-305S protocols"
#endif
#if MWRS_ACTUATION_ENABLED && !MWRS_WHEEL_CALIBRATION_CONFIRMED
#error "Actuation requires verified wheel zero coordinates and direction signs"
#endif

#define MWRS_PROTOCOL_VERSION                1U
#define MWRS_WHEEL_COUNT                     4U
#ifndef MWRS_REQUIRED_WHEEL_COUNT
#define MWRS_REQUIRED_WHEEL_COUNT             4U
#endif
#define MWRS_MAX_FRAME_BYTES                 512U

#if MWRS_REQUIRED_WHEEL_COUNT < 1 || MWRS_REQUIRED_WHEEL_COUNT > MWRS_WHEEL_COUNT
#error "MWRS_REQUIRED_WHEEL_COUNT must be between 1 and 4"
#endif

#define MWRS_PI_COMMAND_TIMEOUT_MS           500U
#define MWRS_STATUS_PERIOD_MS                200U
#define MWRS_DRIVER_HEALTH_PERIOD_MS         500U
#define MWRS_MODBUS_TIMEOUT_MS                20U

/* These limits match the current Raspberry Pi bridge hard limits. */
#define MWRS_MAX_STEERING_ANGLE_RAD          1.5708f
#define MWRS_MAX_DRIVE_VELOCITY_MPS          0.10f
#define MWRS_MAX_STEERING_RATE_RADPS         0.30f
#define MWRS_MAX_DRIVE_ACCELERATION_MPS2     0.10f

/* Mechanical values. The steering ratio is confirmed; drive values are not. */
#define MWRS_STEERING_GEAR_RATIO             30.0f
#define MWRS_MKS_COUNTS_PER_MOTOR_REV        16384.0f
#define MWRS_WHEEL_RADIUS_M                  0.09f
#define MWRS_DRIVE_GEAR_RATIO                20.0f

#define MWRS_STEERING_TOLERANCE_RAD          0.03f
#define MWRS_MKS_POSITION_ACCELERATION       2U
#define MWRS_MKS_MAX_SPEED_RPM               3000U
#define MWRS_BLD_MAX_SPEED_RPM               3000U

/* Both RS-485 buses are configured for 115200, 8N1 in main.c/STM32.ioc. */
#define MWRS_MKS_IDS                         {1U, 2U, 3U, 4U}
#define MWRS_BLD_IDS                         {1U, 2U, 3U, 4U}

/*
 * Replace these values with measurements from the assembled rover.
 * Steering zero is the MKS multi-turn coordinate at wheel angle 0 rad.
 * Direction entries must be either +1 or -1.
 */
#define MWRS_STEERING_ZERO_COORDINATES       {0, 0, 0, 0}
#define MWRS_STEERING_DIRECTION_SIGNS        {1, 1, 1, 1}
#define MWRS_DRIVE_DIRECTION_SIGNS           {1, 1, 1, 1}

#endif
