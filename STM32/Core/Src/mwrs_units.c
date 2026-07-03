#include "mwrs_units.h"

#include <limits.h>
#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static const int32_t steering_zero[MWRS_WHEEL_COUNT] = MWRS_STEERING_ZERO_COORDINATES;
static const int8_t steering_sign[MWRS_WHEEL_COUNT] = MWRS_STEERING_DIRECTION_SIGNS;
static const int8_t drive_sign[MWRS_WHEEL_COUNT] = MWRS_DRIVE_DIRECTION_SIGNS;

static float clamp_float(float value, float low, float high)
{
  if (value < low) return low;
  if (value > high) return high;
  return value;
}

int32_t MWRS_Units_SteeringCoordinate(uint8_t wheel, float wheel_angle_rad)
{
  if (wheel >= MWRS_WHEEL_COUNT)
  {
    return 0;
  }
  double delta = (double)steering_sign[wheel] * (double)wheel_angle_rad /
                 (2.0 * M_PI) * (double)MWRS_STEERING_GEAR_RATIO *
                 (double)MWRS_MKS_COUNTS_PER_MOTOR_REV;
  double coordinate = (double)steering_zero[wheel] + round(delta);
  if (coordinate > (double)INT32_MAX) return INT32_MAX;
  if (coordinate < (double)INT32_MIN) return INT32_MIN;
  return (int32_t)coordinate;
}

int32_t MWRS_Units_SteeringToleranceCounts(void)
{
  double counts = (double)MWRS_STEERING_TOLERANCE_RAD /
                  (2.0 * M_PI) * (double)MWRS_STEERING_GEAR_RATIO *
                  (double)MWRS_MKS_COUNTS_PER_MOTOR_REV;
  return (int32_t)lround(counts);
}

uint16_t MWRS_Units_SteeringSpeedRpm(float wheel_rate_radps)
{
  float rate = clamp_float(fabsf(wheel_rate_radps), 0.0f, MWRS_MAX_STEERING_RATE_RADPS);
  float rpm = rate * MWRS_STEERING_GEAR_RATIO * 60.0f / (2.0f * (float)M_PI);
  long rounded = lroundf(rpm);
  if (rounded < 1L && rate > 0.0f) rounded = 1L;
  if (rounded > (long)MWRS_MKS_MAX_SPEED_RPM) rounded = MWRS_MKS_MAX_SPEED_RPM;
  return (uint16_t)rounded;
}

uint16_t MWRS_Units_DriveSpeedRpm(uint8_t wheel, float velocity_mps, bool *forward)
{
  if (wheel >= MWRS_WHEEL_COUNT || forward == NULL)
  {
    return 0U;
  }
  float signed_velocity = clamp_float(
      velocity_mps, -MWRS_MAX_DRIVE_VELOCITY_MPS, MWRS_MAX_DRIVE_VELOCITY_MPS) *
      (float)drive_sign[wheel];
  *forward = signed_velocity >= 0.0f;
  float rpm = fabsf(signed_velocity) * 60.0f * MWRS_DRIVE_GEAR_RATIO /
              (2.0f * (float)M_PI * MWRS_WHEEL_RADIUS_M);
  long rounded = lroundf(rpm);
  if (rounded > (long)MWRS_BLD_MAX_SPEED_RPM) rounded = MWRS_BLD_MAX_SPEED_RPM;
  return (uint16_t)rounded;
}

float MWRS_Units_RampVelocity(
    float current_mps,
    float target_mps,
    float acceleration_limit_mps2,
    float elapsed_seconds)
{
  if (elapsed_seconds <= 0.0f)
  {
    return current_mps;
  }
  float limit = clamp_float(
      acceleration_limit_mps2, 0.0f, MWRS_MAX_DRIVE_ACCELERATION_MPS2);
  if (limit <= 0.0f)
  {
    return target_mps;
  }
  float maximum_change = limit * elapsed_seconds;
  float delta = target_mps - current_mps;
  delta = clamp_float(delta, -maximum_change, maximum_change);
  return current_mps + delta;
}
