#ifndef MWRS_PROTOCOL_H
#define MWRS_PROTOCOL_H

#include "mwrs_config.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum
{
  MWRS_FAULT_NONE = 0U,
  MWRS_FAULT_CRC = 1001U,
  MWRS_FAULT_FRAME_OVERFLOW = 1002U,
  MWRS_FAULT_JSON = 1003U,
  MWRS_FAULT_FIELDS = 1004U,
  MWRS_FAULT_RANGE = 1005U,
  MWRS_FAULT_COMMAND_TIMEOUT = 2001U,
  MWRS_FAULT_ESTOP = 2002U,
  MWRS_FAULT_HOMING = 2003U,
  MWRS_FAULT_STEERING_BASE = 3101U,
  MWRS_FAULT_DRIVE_BASE = 4101U
};

typedef struct
{
  bool enabled;
  float steering_angle_rad;
  float drive_velocity_mps;
  float steering_limit_radps;
  float acceleration_limit_mps2;
} MwrsWheelTarget;

typedef struct
{
  uint32_t sequence_id;
  uint8_t mode;
  bool enabled;
  bool estop;
  MwrsWheelTarget wheels[MWRS_WHEEL_COUNT];
} MwrsWheelCommand;

typedef struct
{
  bool valid;
  bool sequence_trusted;
  uint32_t fault_code;
} MwrsProtocolParseResult;

uint32_t MWRS_Protocol_Crc32(const uint8_t *data, size_t length);

MwrsProtocolParseResult MWRS_Protocol_ParseWheelFrame(
    const char *frame,
    size_t frame_length,
    MwrsWheelCommand *command);

size_t MWRS_Protocol_EncodeAck(
    char *output,
    size_t output_size,
    uint32_t sequence_id,
    bool accepted,
    uint32_t fault_code);

size_t MWRS_Protocol_EncodeStatus(
    char *output,
    size_t output_size,
    uint32_t sequence_id,
    bool online,
    bool estop,
    bool timeout,
    uint32_t fault_code);

#endif
