#include "mwrs_control.h"

#include "cJSON.h"

#include <math.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

extern UART_HandleTypeDef huart1;
extern UART_HandleTypeDef huart3;
extern UART_HandleTypeDef hlpuart1;

#define PI_UART                 hlpuart1
#define MKS_UART                huart1
#define BLD_UART                huart3

#define COMMAND_TIMEOUT_MS      750U
#define RX_LINE_MAX             2048U
#define CHECKSUM_REQUIRED       0

#define WHEEL_COUNT             4U

#define MODE_STOP               0U
#define MODE_CRAB               1U
#define MODE_SPIN_IN_PLACE      2U
#define MODE_RAW_WHEEL_TEST     3U

/* TODO: Confirm these register addresses against the real MKS SERVO57D manual. */
#define MKS_REG_ENABLE          0x0000U
#define MKS_REG_TARGET_POS_H    0x0001U
#define MKS_REG_TARGET_POS_L    0x0002U
#define MKS_REG_SPEED_LIMIT     0x0003U

/* TODO: Confirm these register addresses against the real BLD-305S manual. */
#define BLD_REG_ENABLE          0x0000U
#define BLD_REG_DIRECTION       0x0001U
#define BLD_REG_SPEED_RPM       0x0002U

#define WHEEL_RADIUS_M          0.10f
#define STEPPER_STEPS_PER_REV   200.0f
#define STEPPER_MICROSTEPS      16.0f
#define STEERING_GEAR_RATIO     30.0f
#define STEERING_STEPS_PER_RAD  ((STEPPER_STEPS_PER_REV * STEPPER_MICROSTEPS * STEERING_GEAR_RATIO) / (2.0f * (float)M_PI))

#define MAX_STEERING_ANGLE_RAD  ((float)M_PI)
#define MAX_STEERING_VEL_RADPS  0.50f
#define MAX_DRIVE_VELOCITY_MPS  0.50f
#define MAX_BLD_RPM             3000

typedef struct
{
  bool enabled;
  float steering_angle_rad;
  float drive_velocity_mps;
  float steering_velocity_limit_radps;
  float drive_acceleration_limit_mps2;
} WheelTarget;

typedef struct
{
  uint32_t sequence_id;
  uint8_t mode_value;
  bool enabled;
  bool estop;
  WheelTarget wheels[WHEEL_COUNT];
} CommandFrame;

static const char *const wheel_names[WHEEL_COUNT] =
{
  "front_left",
  "front_right",
  "rear_left",
  "rear_right"
};

static const uint8_t mks_ids[WHEEL_COUNT] = {1, 2, 3, 4};
static const uint8_t bld_ids[WHEEL_COUNT] = {5, 6, 7, 8};

static char rx_line[RX_LINE_MAX];
static uint16_t rx_len = 0;
static int16_t rx_json_depth = 0;
static bool rx_json_started = false;
static bool rx_in_string = false;
static bool rx_escape_next = false;
static uint32_t last_command_ms = 0;
static uint32_t last_ack_sequence_id = 0;
static bool timeout_active = true;
static bool estop_active = false;
static bool fault_active = false;
static int fault_code = 0;

static uint16_t modbus_crc16(const uint8_t *data, uint16_t len)
{
  uint16_t crc = 0xFFFFU;
  for (uint16_t i = 0; i < len; i++)
  {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; bit++)
    {
      crc = (crc & 1U) ? (uint16_t)((crc >> 1) ^ 0xA001U) : (uint16_t)(crc >> 1);
    }
  }
  return crc;
}

static uint32_t crc32_text(const char *text)
{
  uint32_t crc = 0xFFFFFFFFUL;
  while (*text != '\0')
  {
    crc ^= (uint8_t)(*text++);
    for (uint8_t i = 0; i < 8; i++)
    {
      crc = (crc & 1UL) ? ((crc >> 1) ^ 0xEDB88320UL) : (crc >> 1);
    }
  }
  return crc ^ 0xFFFFFFFFUL;
}

static float clamp_float(float value, float low, float high)
{
  if (value < low) return low;
  if (value > high) return high;
  return value;
}

static void uart_send_text(UART_HandleTypeDef *uart, const char *text)
{
  (void)HAL_UART_Transmit(uart, (uint8_t *)text, (uint16_t)strlen(text), 100U);
}

static void set_rs485_tx(GPIO_TypeDef *port, uint16_t pin, bool tx_enabled)
{
  HAL_GPIO_WritePin(port, pin, tx_enabled ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

static void rs485_transmit(UART_HandleTypeDef *uart, GPIO_TypeDef *dir_port, uint16_t dir_pin,
                           const uint8_t *frame, uint16_t len)
{
  set_rs485_tx(dir_port, dir_pin, true);
  for (volatile uint32_t i = 0; i < 250U; i++) { }
  (void)HAL_UART_Transmit(uart, (uint8_t *)frame, len, 100U);
  while (__HAL_UART_GET_FLAG(uart, UART_FLAG_TC) == RESET) { }
  for (volatile uint32_t i = 0; i < 250U; i++) { }
  set_rs485_tx(dir_port, dir_pin, false);
}

static void modbus_write_single_register(UART_HandleTypeDef *uart, GPIO_TypeDef *dir_port, uint16_t dir_pin,
                                         uint8_t slave_id, uint16_t reg, uint16_t value)
{
  uint8_t frame[8];
  frame[0] = slave_id;
  frame[1] = 0x06U;
  frame[2] = (uint8_t)(reg >> 8);
  frame[3] = (uint8_t)(reg & 0xFFU);
  frame[4] = (uint8_t)(value >> 8);
  frame[5] = (uint8_t)(value & 0xFFU);
  uint16_t crc = modbus_crc16(frame, 6U);
  frame[6] = (uint8_t)(crc & 0xFFU);
  frame[7] = (uint8_t)(crc >> 8);
  rs485_transmit(uart, dir_port, dir_pin, frame, sizeof(frame));
}

static void stop_wheel(uint8_t wheel)
{
  if (wheel >= WHEEL_COUNT) return;

  modbus_write_single_register(&BLD_UART, RS485_DIR2_GPIO_Port, RS485_DIR2_Pin,
                               bld_ids[wheel], BLD_REG_SPEED_RPM, 0U);
  modbus_write_single_register(&BLD_UART, RS485_DIR2_GPIO_Port, RS485_DIR2_Pin,
                               bld_ids[wheel], BLD_REG_ENABLE, 0U);
}

static void stop_all_motors(void)
{
  for (uint8_t i = 0; i < WHEEL_COUNT; i++)
  {
    stop_wheel(i);
  }
}

static void set_steering_target(uint8_t wheel, float angle_rad, float velocity_limit_radps)
{
  angle_rad = clamp_float(angle_rad, -MAX_STEERING_ANGLE_RAD, MAX_STEERING_ANGLE_RAD);
  velocity_limit_radps = clamp_float(velocity_limit_radps, 0.0f, MAX_STEERING_VEL_RADPS);

  int32_t target_steps = (int32_t)lroundf(angle_rad * STEERING_STEPS_PER_RAD);
  uint16_t speed_limit_steps_per_s = (uint16_t)lroundf(velocity_limit_radps * STEERING_STEPS_PER_RAD);
  uint8_t id = mks_ids[wheel];

  modbus_write_single_register(&MKS_UART, RS485_DIR1_GPIO_Port, RS485_DIR1_Pin,
                               id, MKS_REG_SPEED_LIMIT, speed_limit_steps_per_s);
  modbus_write_single_register(&MKS_UART, RS485_DIR1_GPIO_Port, RS485_DIR1_Pin,
                               id, MKS_REG_TARGET_POS_H, (uint16_t)((uint32_t)target_steps >> 16));
  modbus_write_single_register(&MKS_UART, RS485_DIR1_GPIO_Port, RS485_DIR1_Pin,
                               id, MKS_REG_TARGET_POS_L, (uint16_t)((uint32_t)target_steps & 0xFFFFU));
  modbus_write_single_register(&MKS_UART, RS485_DIR1_GPIO_Port, RS485_DIR1_Pin,
                               id, MKS_REG_ENABLE, 1U);
}

static void set_drive_velocity(uint8_t wheel, float velocity_mps)
{
  velocity_mps = clamp_float(velocity_mps, -MAX_DRIVE_VELOCITY_MPS, MAX_DRIVE_VELOCITY_MPS);

  bool forward = velocity_mps >= 0.0f;
  float rpm_f = fabsf(velocity_mps) / (2.0f * (float)M_PI * WHEEL_RADIUS_M) * 60.0f;
  int rpm_i = (int)lroundf(rpm_f);
  if (rpm_i > MAX_BLD_RPM) rpm_i = MAX_BLD_RPM;
  if (rpm_i < 0) rpm_i = 0;

  uint8_t id = bld_ids[wheel];
  modbus_write_single_register(&BLD_UART, RS485_DIR2_GPIO_Port, RS485_DIR2_Pin,
                               id, BLD_REG_DIRECTION, forward ? 1U : 0U);
  modbus_write_single_register(&BLD_UART, RS485_DIR2_GPIO_Port, RS485_DIR2_Pin,
                               id, BLD_REG_SPEED_RPM, (uint16_t)rpm_i);
  modbus_write_single_register(&BLD_UART, RS485_DIR2_GPIO_Port, RS485_DIR2_Pin,
                               id, BLD_REG_ENABLE, rpm_i > 0 ? 1U : 0U);
}

static bool json_get_bool(cJSON *obj, const char *name, bool *out)
{
  cJSON *item = cJSON_GetObjectItemCaseSensitive(obj, name);
  if (!cJSON_IsBool(item)) return false;
  *out = cJSON_IsTrue(item);
  return true;
}

static bool json_get_float(cJSON *obj, const char *name, float *out)
{
  cJSON *item = cJSON_GetObjectItemCaseSensitive(obj, name);
  if (!cJSON_IsNumber(item)) return false;
  *out = (float)item->valuedouble;
  return true;
}

static bool parse_command(const char *line, CommandFrame *cmd, char *err, uint16_t err_size)
{
  cJSON *root = cJSON_Parse(line);
  if (root == NULL)
  {
    snprintf(err, err_size, "json_parse_failed");
    return false;
  }

  cJSON *payload = cJSON_GetObjectItemCaseSensitive(root, "payload");
  if (!cJSON_IsObject(payload))
  {
    snprintf(err, err_size, "missing_payload");
    cJSON_Delete(root);
    return false;
  }

#if CHECKSUM_REQUIRED
  cJSON *checksum = cJSON_GetObjectItemCaseSensitive(root, "checksum");
  char *payload_text = cJSON_PrintUnformatted(payload);
  uint32_t got = cJSON_IsNumber(checksum) ? (uint32_t)checksum->valuedouble : 0U;
  uint32_t want = payload_text != NULL ? crc32_text(payload_text) : 0U;
  if (payload_text != NULL) cJSON_free(payload_text);
  if (!cJSON_IsNumber(checksum) || got != want)
  {
    snprintf(err, err_size, "checksum_failed");
    cJSON_Delete(root);
    return false;
  }
#else
  (void)crc32_text;
#endif

  cJSON *type = cJSON_GetObjectItemCaseSensitive(payload, "type");
  cJSON *seq = cJSON_GetObjectItemCaseSensitive(payload, "sequence_id");
  cJSON *mode_value = cJSON_GetObjectItemCaseSensitive(payload, "mode_value");
  cJSON *wheels = cJSON_GetObjectItemCaseSensitive(payload, "wheels");

  if (!cJSON_IsString(type) || strcmp(type->valuestring, "SET_WHEEL_TARGETS") != 0)
  {
    snprintf(err, err_size, "bad_type");
    cJSON_Delete(root);
    return false;
  }
  if (!cJSON_IsNumber(seq) || !cJSON_IsNumber(mode_value))
  {
    snprintf(err, err_size, "missing_sequence_or_mode");
    cJSON_Delete(root);
    return false;
  }
  if (!json_get_bool(payload, "enabled", &cmd->enabled) ||
      !json_get_bool(payload, "estop", &cmd->estop))
  {
    snprintf(err, err_size, "missing_enabled_or_estop");
    cJSON_Delete(root);
    return false;
  }
  if (!cJSON_IsArray(wheels) || cJSON_GetArraySize(wheels) != WHEEL_COUNT)
  {
    snprintf(err, err_size, "wheel_count_not_4");
    cJSON_Delete(root);
    return false;
  }

  cmd->sequence_id = (uint32_t)seq->valuedouble;
  cmd->mode_value = (uint8_t)mode_value->valuedouble;
  if (cmd->mode_value > MODE_RAW_WHEEL_TEST)
  {
    snprintf(err, err_size, "unknown_mode");
    cJSON_Delete(root);
    return false;
  }

  uint8_t enabled_wheels = 0;
  for (uint8_t i = 0; i < WHEEL_COUNT; i++)
  {
    cJSON *wheel = cJSON_GetArrayItem(wheels, i);
    cJSON *name = cJSON_GetObjectItemCaseSensitive(wheel, "name");
    if (!cJSON_IsObject(wheel) || !cJSON_IsString(name) ||
        strcmp(name->valuestring, wheel_names[i]) != 0)
    {
      snprintf(err, err_size, "wheel_order_error");
      cJSON_Delete(root);
      return false;
    }

    WheelTarget *target = &cmd->wheels[i];
    if (!json_get_bool(wheel, "enabled", &target->enabled) ||
        !json_get_float(wheel, "steering_angle_rad", &target->steering_angle_rad) ||
        !json_get_float(wheel, "drive_velocity_mps", &target->drive_velocity_mps) ||
        !json_get_float(wheel, "steering_velocity_limit_radps", &target->steering_velocity_limit_radps) ||
        !json_get_float(wheel, "drive_acceleration_limit_mps2", &target->drive_acceleration_limit_mps2))
    {
      snprintf(err, err_size, "wheel_field_missing");
      cJSON_Delete(root);
      return false;
    }

    if (fabsf(target->steering_angle_rad) > MAX_STEERING_ANGLE_RAD ||
        fabsf(target->drive_velocity_mps) > MAX_DRIVE_VELOCITY_MPS)
    {
      snprintf(err, err_size, "target_out_of_range");
      cJSON_Delete(root);
      return false;
    }

    if (target->enabled) enabled_wheels++;
    if (!target->enabled && fabsf(target->drive_velocity_mps) > 0.001f)
    {
      snprintf(err, err_size, "disabled_wheel_has_speed");
      cJSON_Delete(root);
      return false;
    }
  }

  if (cmd->mode_value == MODE_RAW_WHEEL_TEST && enabled_wheels != 1U)
  {
    snprintf(err, err_size, "raw_test_needs_one_wheel");
    cJSON_Delete(root);
    return false;
  }

  cJSON_Delete(root);
  return true;
}

static void send_ack(uint32_t sequence_id, const char *message)
{
  char tx[128];
  snprintf(tx, sizeof(tx), "{\"type\":\"ACK\",\"sequence_id\":%lu,\"message\":\"%s\"}\n",
           (unsigned long)sequence_id, message);
  uart_send_text(&PI_UART, tx);
}

static void send_status(const char *message)
{
  char tx[192];
  snprintf(tx, sizeof(tx),
           "{\"type\":\"STATUS\",\"last_ack_sequence_id\":%lu,\"online\":true,"
           "\"fault\":%s,\"fault_code\":%d,\"estop_active\":%s,\"timeout\":%s,"
           "\"message\":\"%s\"}\n",
           (unsigned long)last_ack_sequence_id,
           fault_active ? "true" : "false",
           fault_code,
           estop_active ? "true" : "false",
           timeout_active ? "true" : "false",
           message);
  uart_send_text(&PI_UART, tx);
}

static void execute_command(const CommandFrame *cmd)
{
  last_command_ms = HAL_GetTick();
  last_ack_sequence_id = cmd->sequence_id;
  timeout_active = false;
  estop_active = cmd->estop;
  fault_active = false;
  fault_code = 0;

  if (cmd->estop)
  {
    stop_all_motors();
    send_ack(cmd->sequence_id, "estop");
    send_status("estop");
    return;
  }

  if (!cmd->enabled || cmd->mode_value == MODE_STOP)
  {
    stop_all_motors();
    send_ack(cmd->sequence_id, cmd->enabled ? "stop" : "disabled");
    send_status(cmd->enabled ? "stop" : "disabled");
    return;
  }

  for (uint8_t i = 0; i < WHEEL_COUNT; i++)
  {
    if (!cmd->wheels[i].enabled)
    {
      stop_wheel(i);
      continue;
    }

    set_steering_target(i, cmd->wheels[i].steering_angle_rad,
                        cmd->wheels[i].steering_velocity_limit_radps);
    set_drive_velocity(i, cmd->wheels[i].drive_velocity_mps);
  }

  send_ack(cmd->sequence_id, "ok");
  send_status("ok");
}

static void handle_line(const char *line)
{
  CommandFrame cmd;
  char err[64];

  if (!parse_command(line, &cmd, err, sizeof(err)))
  {
    stop_all_motors();
    fault_active = true;
    fault_code = 1;
    send_status(err);
    return;
  }

  execute_command(&cmd);
}

static void reset_rx_frame(void)
{
  rx_len = 0U;
  rx_json_depth = 0;
  rx_json_started = false;
  rx_in_string = false;
  rx_escape_next = false;
}

static void update_json_frame_state(uint8_t ch)
{
  if (rx_escape_next)
  {
    rx_escape_next = false;
    return;
  }

  if (rx_in_string)
  {
    if (ch == '\\')
    {
      rx_escape_next = true;
    }
    else if (ch == '"')
    {
      rx_in_string = false;
    }
    return;
  }

  if (ch == '"')
  {
    rx_in_string = true;
  }
  else if (ch == '{' || ch == '[')
  {
    rx_json_started = true;
    rx_json_depth++;
  }
  else if (ch == '}' || ch == ']')
  {
    rx_json_depth--;
  }
}

static void poll_pi_uart(void)
{
  uint8_t ch;
  while (HAL_UART_Receive(&PI_UART, &ch, 1U, 0U) == HAL_OK)
  {
    if (!rx_json_started &&
        (ch == ' ' || ch == '\t' || ch == '\r' || ch == '\n'))
    {
      continue;
    }

    if (rx_len < (RX_LINE_MAX - 1U))
    {
      rx_line[rx_len++] = (char)ch;
      update_json_frame_state(ch);

      if (rx_json_started && rx_json_depth == 0 && !rx_in_string)
      {
        rx_line[rx_len] = '\0';
        handle_line(rx_line);
        reset_rx_frame();
        return;
      }

      if (rx_json_depth < 0)
      {
        reset_rx_frame();
        stop_all_motors();
        fault_active = true;
        fault_code = 3;
        send_status("json_bracket_error");
        return;
      }
    }
    else
    {
      reset_rx_frame();
      stop_all_motors();
      fault_active = true;
      fault_code = 2;
      send_status("rx_line_too_long");
    }
  }
}

static void poll_timeout(void)
{
  if (!timeout_active && (HAL_GetTick() - last_command_ms > COMMAND_TIMEOUT_MS))
  {
    timeout_active = true;
    stop_all_motors();
    send_status("command_timeout");
  }
}

void MWRS_Control_Init(void)
{
  HAL_GPIO_WritePin(RS485_DIR1_GPIO_Port, RS485_DIR1_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(RS485_DIR2_GPIO_Port, RS485_DIR2_Pin, GPIO_PIN_RESET);

  last_command_ms = HAL_GetTick();
  timeout_active = true;
  estop_active = false;
  fault_active = false;
  fault_code = 0;
  reset_rx_frame();

  stop_all_motors();
  send_status("boot");
}

void MWRS_Control_Process(void)
{
  poll_pi_uart();
  poll_timeout();
}
