#ifndef MWRS_DRIVERS_H
#define MWRS_DRIVERS_H

#include "mwrs_config.h"

#include <stdbool.h>
#include <stdint.h>

typedef struct
{
  bool steering_online;
  bool drive_online;
  bool homed;
  bool steering_fault;
  bool drive_fault;
  int64_t steering_coordinate;
  uint16_t drive_speed_rpm;
  uint16_t drive_run_state;
  uint16_t drive_fault_raw;
} MwrsDriverStatus;

void MWRS_Drivers_Init(void);
bool MWRS_Drivers_ReadStatus(uint8_t wheel, MwrsDriverStatus *status);
bool MWRS_Drivers_SetSteering(
    uint8_t wheel,
    int32_t target_coordinate,
    uint16_t speed_rpm);
bool MWRS_Drivers_ReadSteeringCoordinate(uint8_t wheel, int64_t *coordinate);
bool MWRS_Drivers_SetDrive(uint8_t wheel, uint16_t speed_rpm, bool forward);
bool MWRS_Drivers_StopDrive(uint8_t wheel, bool brake);
bool MWRS_Drivers_StopWheel(uint8_t wheel, bool emergency);
bool MWRS_Drivers_StopAll(uint8_t wheel_count, bool emergency);

#endif
