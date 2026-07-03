#ifndef MWRS_UNITS_H
#define MWRS_UNITS_H

#include "mwrs_config.h"

#include <stdbool.h>
#include <stdint.h>

int32_t MWRS_Units_SteeringCoordinate(uint8_t wheel, float wheel_angle_rad);
int32_t MWRS_Units_SteeringToleranceCounts(void);
uint16_t MWRS_Units_SteeringSpeedRpm(float wheel_rate_radps);
uint16_t MWRS_Units_DriveSpeedRpm(uint8_t wheel, float velocity_mps, bool *forward);
float MWRS_Units_RampVelocity(
    float current_mps,
    float target_mps,
    float acceleration_limit_mps2,
    float elapsed_seconds);

#endif
