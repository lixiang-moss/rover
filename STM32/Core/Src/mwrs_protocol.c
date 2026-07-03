#include "mwrs_protocol.h"

#include "cJSON.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static const char *const wheel_frame_keys[] = {"v", "t", "q", "m", "e", "s", "w"};

uint32_t MWRS_Protocol_Crc32(const uint8_t *data, size_t length)
{
  uint32_t crc = 0xFFFFFFFFUL;
  for (size_t byte_index = 0U; byte_index < length; byte_index++)
  {
    crc ^= data[byte_index];
    for (uint8_t bit = 0U; bit < 8U; bit++)
    {
      crc = (crc & 1UL) != 0UL ? (crc >> 1) ^ 0xEDB88320UL : crc >> 1;
    }
  }
  return crc ^ 0xFFFFFFFFUL;
}

static bool is_upper_hex(char value)
{
  return (value >= '0' && value <= '9') || (value >= 'A' && value <= 'F');
}

static uint8_t hex_value(char value)
{
  return value <= '9' ? (uint8_t)(value - '0') : (uint8_t)(value - 'A' + 10);
}

static bool object_has_exact_keys(
    const cJSON *object,
    const char *const *keys,
    size_t key_count)
{
  if (!cJSON_IsObject(object) || key_count > 31U)
  {
    return false;
  }

  uint32_t seen = 0U;
  size_t child_count = 0U;
  for (const cJSON *child = object->child; child != NULL; child = child->next)
  {
    bool matched = false;
    for (size_t key_index = 0U; key_index < key_count; key_index++)
    {
      if (child->string != NULL && strcmp(child->string, keys[key_index]) == 0)
      {
        uint32_t bit = 1UL << key_index;
        if ((seen & bit) != 0U)
        {
          return false;
        }
        seen |= bit;
        matched = true;
        break;
      }
    }
    if (!matched)
    {
      return false;
    }
    child_count++;
  }

  uint32_t expected = (1UL << key_count) - 1UL;
  return child_count == key_count && seen == expected;
}

static bool json_uint32(const cJSON *item, uint32_t *value)
{
  if (!cJSON_IsNumber(item) || !isfinite(item->valuedouble) ||
      item->valuedouble < 0.0 || item->valuedouble > 4294967295.0 ||
      floor(item->valuedouble) != item->valuedouble)
  {
    return false;
  }
  *value = (uint32_t)item->valuedouble;
  return true;
}

static bool json_uint8_in_range(const cJSON *item, uint8_t maximum, uint8_t *value)
{
  uint32_t temporary = 0U;
  if (!json_uint32(item, &temporary) || temporary > maximum)
  {
    return false;
  }
  *value = (uint8_t)temporary;
  return true;
}

static bool json_binary(const cJSON *item, bool *value)
{
  uint8_t temporary = 0U;
  if (!json_uint8_in_range(item, 1U, &temporary))
  {
    return false;
  }
  *value = temporary == 1U;
  return true;
}

static bool json_finite_float(const cJSON *item, float *value)
{
  if (!cJSON_IsNumber(item) || !isfinite(item->valuedouble))
  {
    return false;
  }
  float converted = (float)item->valuedouble;
  if (!isfinite(converted))
  {
    return false;
  }
  *value = converted;
  return true;
}

static MwrsProtocolParseResult parse_error(uint32_t fault_code, bool sequence_trusted)
{
  MwrsProtocolParseResult result = {false, sequence_trusted, fault_code};
  return result;
}

MwrsProtocolParseResult MWRS_Protocol_ParseWheelFrame(
    const char *frame,
    size_t frame_length,
    MwrsWheelCommand *command)
{
  if (frame == NULL || command == NULL || frame_length == 0U ||
      frame_length >= MWRS_MAX_FRAME_BYTES)
  {
    return parse_error(MWRS_FAULT_FRAME_OVERFLOW, false);
  }
  if (frame_length < 11U || frame[frame_length - 9U] != '*')
  {
    return parse_error(MWRS_FAULT_CRC, false);
  }

  uint32_t received_crc = 0U;
  for (size_t index = frame_length - 8U; index < frame_length; index++)
  {
    if (!is_upper_hex(frame[index]))
    {
      return parse_error(MWRS_FAULT_CRC, false);
    }
    received_crc = (received_crc << 4) | hex_value(frame[index]);
  }

  size_t json_length = frame_length - 9U;
  uint32_t expected_crc = MWRS_Protocol_Crc32((const uint8_t *)frame, json_length);
  if (received_crc != expected_crc)
  {
    return parse_error(MWRS_FAULT_CRC, false);
  }

  char json_text[MWRS_MAX_FRAME_BYTES];
  memcpy(json_text, frame, json_length);
  json_text[json_length] = '\0';

  const char *parse_end = NULL;
  cJSON *root = cJSON_ParseWithLengthOpts(
      json_text, json_length + 1U, &parse_end, 1);
  if (root == NULL || parse_end != json_text + json_length)
  {
    cJSON_Delete(root);
    return parse_error(MWRS_FAULT_JSON, false);
  }
  if (!object_has_exact_keys(
          root,
          wheel_frame_keys,
          sizeof(wheel_frame_keys) / sizeof(wheel_frame_keys[0])))
  {
    cJSON_Delete(root);
    return parse_error(MWRS_FAULT_FIELDS, false);
  }

  memset(command, 0, sizeof(*command));
  cJSON *version = cJSON_GetObjectItemCaseSensitive(root, "v");
  cJSON *type = cJSON_GetObjectItemCaseSensitive(root, "t");
  cJSON *sequence = cJSON_GetObjectItemCaseSensitive(root, "q");
  cJSON *mode = cJSON_GetObjectItemCaseSensitive(root, "m");
  cJSON *enabled = cJSON_GetObjectItemCaseSensitive(root, "e");
  cJSON *estop = cJSON_GetObjectItemCaseSensitive(root, "s");
  cJSON *wheels = cJSON_GetObjectItemCaseSensitive(root, "w");

  uint32_t protocol_version = 0U;
  if (!json_uint32(sequence, &command->sequence_id))
  {
    cJSON_Delete(root);
    return parse_error(MWRS_FAULT_FIELDS, false);
  }
  bool sequence_trusted = true;
  if (!json_uint32(version, &protocol_version) || protocol_version != MWRS_PROTOCOL_VERSION ||
      !cJSON_IsString(type) || type->valuestring == NULL || strcmp(type->valuestring, "W") != 0 ||
      !json_uint8_in_range(mode, 3U, &command->mode) ||
      !json_binary(enabled, &command->enabled) ||
      !json_binary(estop, &command->estop))
  {
    cJSON_Delete(root);
    return parse_error(MWRS_FAULT_FIELDS, sequence_trusted);
  }
  if (!cJSON_IsArray(wheels) || cJSON_GetArraySize(wheels) != (int)MWRS_WHEEL_COUNT)
  {
    cJSON_Delete(root);
    return parse_error(MWRS_FAULT_RANGE, sequence_trusted);
  }

  uint8_t enabled_wheels = 0U;
  for (uint8_t wheel_index = 0U; wheel_index < MWRS_WHEEL_COUNT; wheel_index++)
  {
    cJSON *wheel = cJSON_GetArrayItem(wheels, wheel_index);
    if (!cJSON_IsArray(wheel) || cJSON_GetArraySize(wheel) != 5)
    {
      cJSON_Delete(root);
      return parse_error(MWRS_FAULT_RANGE, sequence_trusted);
    }

    MwrsWheelTarget *target = &command->wheels[wheel_index];
    if (!json_binary(cJSON_GetArrayItem(wheel, 0), &target->enabled) ||
        !json_finite_float(cJSON_GetArrayItem(wheel, 1), &target->steering_angle_rad) ||
        !json_finite_float(cJSON_GetArrayItem(wheel, 2), &target->drive_velocity_mps) ||
        !json_finite_float(cJSON_GetArrayItem(wheel, 3), &target->steering_limit_radps) ||
        !json_finite_float(cJSON_GetArrayItem(wheel, 4), &target->acceleration_limit_mps2))
    {
      cJSON_Delete(root);
      return parse_error(MWRS_FAULT_RANGE, sequence_trusted);
    }
    if (fabsf(target->steering_angle_rad) > MWRS_MAX_STEERING_ANGLE_RAD ||
        fabsf(target->drive_velocity_mps) > MWRS_MAX_DRIVE_VELOCITY_MPS ||
        target->steering_limit_radps < 0.0f ||
        target->steering_limit_radps > MWRS_MAX_STEERING_RATE_RADPS ||
        target->acceleration_limit_mps2 < 0.0f ||
        target->acceleration_limit_mps2 > MWRS_MAX_DRIVE_ACCELERATION_MPS2)
    {
      cJSON_Delete(root);
      return parse_error(MWRS_FAULT_RANGE, sequence_trusted);
    }
    if (target->enabled)
    {
      enabled_wheels++;
    }
  }

  if (command->enabled &&
      ((command->mode == 3U && enabled_wheels != 1U) ||
       ((command->mode == 1U || command->mode == 2U) && enabled_wheels != MWRS_WHEEL_COUNT)))
  {
    cJSON_Delete(root);
    return parse_error(MWRS_FAULT_RANGE, sequence_trusted);
  }

  cJSON_Delete(root);
  MwrsProtocolParseResult result = {true, true, MWRS_FAULT_NONE};
  return result;
}

static size_t append_crc(char *output, size_t output_size, int json_length)
{
  if (output == NULL || output_size == 0U || json_length <= 0 ||
      (size_t)json_length >= output_size)
  {
    return 0U;
  }
  uint32_t crc = MWRS_Protocol_Crc32((const uint8_t *)output, (size_t)json_length);
  int frame_length = snprintf(
      output + json_length,
      output_size - (size_t)json_length,
      "*%08lX\n",
      (unsigned long)crc);
  if (frame_length != 10 || (size_t)json_length + (size_t)frame_length >= output_size)
  {
    output[0] = '\0';
    return 0U;
  }
  return (size_t)json_length + (size_t)frame_length;
}

size_t MWRS_Protocol_EncodeAck(
    char *output,
    size_t output_size,
    uint32_t sequence_id,
    bool accepted,
    uint32_t fault_code)
{
  int json_length = snprintf(
      output,
      output_size,
      "{\"fc\":%lu,\"ok\":%u,\"q\":%lu,\"t\":\"A\",\"v\":1}",
      (unsigned long)fault_code,
      accepted ? 1U : 0U,
      (unsigned long)sequence_id);
  return append_crc(output, output_size, json_length);
}

size_t MWRS_Protocol_EncodeStatus(
    char *output,
    size_t output_size,
    uint32_t sequence_id,
    bool online,
    bool estop,
    bool timeout,
    uint32_t fault_code)
{
  int json_length = snprintf(
      output,
      output_size,
      "{\"es\":%u,\"fc\":%lu,\"on\":%u,\"q\":%lu,\"t\":\"S\",\"to\":%u,\"v\":1}",
      estop ? 1U : 0U,
      (unsigned long)fault_code,
      online ? 1U : 0U,
      (unsigned long)sequence_id,
      timeout ? 1U : 0U);
  return append_crc(output, output_size, json_length);
}
