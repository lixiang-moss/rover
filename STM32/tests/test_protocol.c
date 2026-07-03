#include "mwrs_protocol.h"
#include "mwrs_units.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static size_t make_frame(const char *json, char *frame, size_t frame_size)
{
  uint32_t crc = MWRS_Protocol_Crc32((const uint8_t *)json, strlen(json));
  int length = snprintf(
      frame, frame_size, "%s*%08lX", json, (unsigned long)crc);
  assert(length > 0 && (size_t)length < frame_size);
  return (size_t)length;
}

static void test_fixed_command_vector(void)
{
  const char *frame =
      "{\"e\":1,\"m\":3,\"q\":42,\"s\":0,\"t\":\"W\",\"v\":1,\"w\":"
      "[[1,0.1,0.08,0.15,0.05],[0,0.0,0.0,0.15,0.05],"
      "[0,0.0,0.0,0.15,0.05],[0,0.0,0.0,0.15,0.05]]}*58782C06";
  MwrsWheelCommand command;
  MwrsProtocolParseResult result = MWRS_Protocol_ParseWheelFrame(
      frame, strlen(frame), &command);
  assert(result.valid);
  assert(command.sequence_id == 42U);
  assert(command.mode == 3U);
  assert(command.enabled && !command.estop);
  assert(command.wheels[0].enabled);
  assert(fabsf(command.wheels[0].drive_velocity_mps - 0.08f) < 1e-6f);
}

static void test_response_vectors(void)
{
  char frame[160];
  size_t length = MWRS_Protocol_EncodeAck(frame, sizeof(frame), 42U, true, 0U);
  assert(length == strlen(frame));
  assert(strcmp(
             frame,
             "{\"fc\":0,\"ok\":1,\"q\":42,\"t\":\"A\",\"v\":1}*88B875B3\n") == 0);

  length = MWRS_Protocol_EncodeStatus(
      frame, sizeof(frame), 42U, true, false, false, 0U);
  assert(length == strlen(frame));
  assert(strcmp(
             frame,
             "{\"es\":0,\"fc\":0,\"on\":1,\"q\":42,\"t\":\"S\",\"to\":0,\"v\":1}*F18BB4D1\n") == 0);
}

static void test_invalid_frames(void)
{
  const char *bad_crc =
      "{\"e\":0,\"m\":0,\"q\":1,\"s\":0,\"t\":\"W\",\"v\":1,\"w\":"
      "[[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]]}*00000000";
  MwrsWheelCommand command;
  MwrsProtocolParseResult result = MWRS_Protocol_ParseWheelFrame(
      bad_crc, strlen(bad_crc), &command);
  assert(!result.valid && result.fault_code == MWRS_FAULT_CRC);

  char frame[512];
  const char *extra_field =
      "{\"e\":0,\"m\":0,\"q\":7,\"s\":0,\"t\":\"W\",\"v\":1,\"w\":"
      "[[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0],[0,0,0,0,0]],\"x\":1}";
  size_t length = make_frame(extra_field, frame, sizeof(frame));
  result = MWRS_Protocol_ParseWheelFrame(frame, length, &command);
  assert(!result.valid && result.fault_code == MWRS_FAULT_FIELDS);

  const char *excess_speed =
      "{\"e\":1,\"m\":3,\"q\":8,\"s\":0,\"t\":\"W\",\"v\":1,\"w\":"
      "[[1,0,0.11,0.15,0.05],[0,0,0,0.15,0.05],[0,0,0,0.15,0.05],"
      "[0,0,0,0.15,0.05]]}";
  length = make_frame(excess_speed, frame, sizeof(frame));
  result = MWRS_Protocol_ParseWheelFrame(frame, length, &command);
  assert(!result.valid && result.sequence_trusted && result.fault_code == MWRS_FAULT_RANGE);
}

static void test_unit_conversions(void)
{
  assert(MWRS_Units_SteeringCoordinate(0U, 0.0f) == 0);
  assert(MWRS_Units_SteeringCoordinate(0U, 0.1f) == 7823);
  assert(MWRS_Units_SteeringToleranceCounts() == 2347);
  assert(MWRS_Units_SteeringSpeedRpm(0.15f) == 43U);

  bool forward = false;
  assert(MWRS_Units_DriveSpeedRpm(0U, 0.08f, &forward) == 170U);
  assert(forward);
  assert(MWRS_Units_DriveSpeedRpm(0U, -0.08f, &forward) == 170U);
  assert(!forward);

  float ramped = MWRS_Units_RampVelocity(0.0f, 0.08f, 0.05f, 0.1f);
  assert(fabsf(ramped - 0.005f) < 1e-6f);
}

int main(void)
{
  test_fixed_command_vector();
  test_response_vectors();
  test_invalid_frames();
  test_unit_conversions();
  puts("STM32 host protocol/unit tests passed");
  return 0;
}
