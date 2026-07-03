#include "mwrs_control.h"

#include "mwrs_config.h"
#include "mwrs_drivers.h"
#include "mwrs_protocol.h"
#include "mwrs_units.h"

#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

extern UART_HandleTypeDef hlpuart1;

#define PI_UART hlpuart1
#define PI_RX_RING_BYTES 1024U

static volatile uint8_t pi_rx_ring[PI_RX_RING_BYTES];
static volatile uint16_t pi_rx_head = 0U;
static volatile uint16_t pi_rx_tail = 0U;
static volatile uint8_t pi_rx_byte = 0U;
static volatile bool pi_rx_overflow = false;

static char rx_frame[MWRS_MAX_FRAME_BYTES];
static uint16_t rx_frame_length = 0U;
static bool discard_until_newline = false;

static uint32_t last_valid_command_ms = 0U;
static uint32_t last_status_ms = 0U;
static uint32_t last_health_poll_ms = 0U;
static uint32_t last_execution_ms = 0U;
static uint32_t last_sequence_id = 0U;

static bool command_timeout = true;
static bool software_estop = false;
static bool outputs_active = false;
static uint32_t protocol_fault_code = MWRS_FAULT_NONE;

static MwrsDriverStatus driver_status[MWRS_WHEEL_COUNT];
static float applied_drive_velocity[MWRS_WHEEL_COUNT];
static bool wheel_output_active[MWRS_WHEEL_COUNT];

__weak bool MWRS_HardwareEstopActive(void)
{
  /* Fail safe if the configuration flag is enabled without a board override. */
  return true;
}

static bool hardware_estop_active(void)
{
#if MWRS_HARDWARE_ESTOP_CONFIGURED
  return MWRS_HardwareEstopActive();
#else
  return false;
#endif
}

static void pi_send(const char *frame, size_t frame_length)
{
  if (frame != NULL && frame_length > 0U && frame_length <= UINT16_MAX)
  {
    (void)HAL_UART_Transmit(
        &PI_UART, (uint8_t *)frame, (uint16_t)frame_length, 100U);
  }
}

static bool drivers_ready(void)
{
#if !MWRS_ACTUATION_ENABLED || !MWRS_HARDWARE_ESTOP_CONFIGURED
  return false;
#else
  for (uint8_t wheel = 0U; wheel < MWRS_REQUIRED_WHEEL_COUNT; wheel++)
  {
    const MwrsDriverStatus *status = &driver_status[wheel];
    if (!status->steering_online || !status->drive_online || !status->homed ||
        status->steering_fault || status->drive_fault)
    {
      return false;
    }
  }
  return true;
#endif
}

static uint32_t effective_fault_code(void)
{
  if (hardware_estop_active() || software_estop)
  {
    return MWRS_FAULT_ESTOP;
  }
  if (command_timeout)
  {
    return MWRS_FAULT_COMMAND_TIMEOUT;
  }
#if MWRS_ACTUATION_ENABLED
  for (uint8_t wheel = 0U; wheel < MWRS_REQUIRED_WHEEL_COUNT; wheel++)
  {
    if (!driver_status[wheel].steering_online || driver_status[wheel].steering_fault)
    {
      return MWRS_FAULT_STEERING_BASE + wheel;
    }
  }
  for (uint8_t wheel = 0U; wheel < MWRS_REQUIRED_WHEEL_COUNT; wheel++)
  {
    if (!driver_status[wheel].drive_online || driver_status[wheel].drive_fault)
    {
      return MWRS_FAULT_DRIVE_BASE + wheel;
    }
  }
  for (uint8_t wheel = 0U; wheel < MWRS_REQUIRED_WHEEL_COUNT; wheel++)
  {
    if (!driver_status[wheel].homed)
    {
      return MWRS_FAULT_HOMING;
    }
  }
#endif
  return protocol_fault_code;
}

static void reset_applied_velocities(void)
{
  memset(applied_drive_velocity, 0, sizeof(applied_drive_velocity));
  last_execution_ms = HAL_GetTick();
}

static void stop_outputs(bool emergency, bool force)
{
#if MWRS_ACTUATION_ENABLED
  if (force || outputs_active)
  {
    if (!MWRS_Drivers_StopAll(MWRS_REQUIRED_WHEEL_COUNT, emergency))
    {
      for (uint8_t wheel = 0U; wheel < MWRS_REQUIRED_WHEEL_COUNT; wheel++)
      {
        driver_status[wheel].steering_online = false;
        driver_status[wheel].drive_online = false;
      }
    }
  }
#else
  (void)emergency;
  (void)force;
#endif
  outputs_active = false;
  memset(wheel_output_active, 0, sizeof(wheel_output_active));
  reset_applied_velocities();
}

static void send_ack(uint32_t sequence_id, bool accepted, uint32_t fault_code)
{
  char frame[128];
  size_t length = MWRS_Protocol_EncodeAck(
      frame, sizeof(frame), sequence_id, accepted, fault_code);
  pi_send(frame, length);
}

static void send_status(void)
{
  char frame[160];
  bool estop = hardware_estop_active() || software_estop;
  size_t length = MWRS_Protocol_EncodeStatus(
      frame,
      sizeof(frame),
      last_sequence_id,
      drivers_ready(),
      estop,
      command_timeout,
      effective_fault_code());
  pi_send(frame, length);
}

static void poll_driver_health(bool force)
{
#if MWRS_ACTUATION_ENABLED
  uint32_t now = HAL_GetTick();
  if (!force && now - last_health_poll_ms < MWRS_DRIVER_HEALTH_PERIOD_MS)
  {
    return;
  }
  last_health_poll_ms = now;
  for (uint8_t wheel = 0U; wheel < MWRS_REQUIRED_WHEEL_COUNT; wheel++)
  {
    (void)MWRS_Drivers_ReadStatus(wheel, &driver_status[wheel]);
  }
  if (effective_fault_code() >= MWRS_FAULT_STEERING_BASE && outputs_active)
  {
    stop_outputs(true, true);
  }
#else
  (void)force;
#endif
}

static bool command_uses_configured_wheels(const MwrsWheelCommand *command)
{
  for (uint8_t wheel = MWRS_REQUIRED_WHEEL_COUNT; wheel < MWRS_WHEEL_COUNT; wheel++)
  {
    if (command->wheels[wheel].enabled)
    {
      return false;
    }
  }
  return true;
}

static bool apply_motion_command(const MwrsWheelCommand *command)
{
#if !MWRS_ACTUATION_ENABLED
  (void)command;
  return false;
#else
  uint32_t now = HAL_GetTick();
  float elapsed_seconds = (float)(now - last_execution_ms) / 1000.0f;
  if (elapsed_seconds > 0.10f)
  {
    elapsed_seconds = 0.10f;
  }
  last_execution_ms = now;

  int32_t targets[MWRS_WHEEL_COUNT] = {0};
  bool steering_ready[MWRS_WHEEL_COUNT] = {false};

  for (uint8_t wheel = 0U; wheel < MWRS_REQUIRED_WHEEL_COUNT; wheel++)
  {
    const MwrsWheelTarget *target = &command->wheels[wheel];
    if (!target->enabled)
    {
      if (wheel_output_active[wheel] && !MWRS_Drivers_StopWheel(wheel, false))
      {
        driver_status[wheel].steering_online = false;
        driver_status[wheel].drive_online = false;
        return false;
      }
      wheel_output_active[wheel] = false;
      applied_drive_velocity[wheel] = 0.0f;
      continue;
    }

    targets[wheel] = MWRS_Units_SteeringCoordinate(wheel, target->steering_angle_rad);
    uint16_t steering_rpm = MWRS_Units_SteeringSpeedRpm(target->steering_limit_radps);
    if (!MWRS_Drivers_SetSteering(wheel, targets[wheel], steering_rpm))
    {
      driver_status[wheel].steering_online = false;
      return false;
    }
    wheel_output_active[wheel] = true;
  }

  int32_t tolerance = MWRS_Units_SteeringToleranceCounts();
  for (uint8_t wheel = 0U; wheel < MWRS_REQUIRED_WHEEL_COUNT; wheel++)
  {
    if (!command->wheels[wheel].enabled)
    {
      continue;
    }
    int64_t coordinate = 0;
    if (!MWRS_Drivers_ReadSteeringCoordinate(wheel, &coordinate))
    {
      driver_status[wheel].steering_online = false;
      return false;
    }
    driver_status[wheel].steering_coordinate = coordinate;
    steering_ready[wheel] = llabs(coordinate - (int64_t)targets[wheel]) <= tolerance;
  }

  for (uint8_t wheel = 0U; wheel < MWRS_REQUIRED_WHEEL_COUNT; wheel++)
  {
    const MwrsWheelTarget *target = &command->wheels[wheel];
    if (!target->enabled || !steering_ready[wheel])
    {
      if (!MWRS_Drivers_SetDrive(wheel, 0U, true))
      {
        driver_status[wheel].drive_online = false;
        return false;
      }
      applied_drive_velocity[wheel] = 0.0f;
      continue;
    }

    applied_drive_velocity[wheel] = MWRS_Units_RampVelocity(
        applied_drive_velocity[wheel],
        target->drive_velocity_mps,
        target->acceleration_limit_mps2,
        elapsed_seconds);
    bool forward = true;
    uint16_t drive_rpm = MWRS_Units_DriveSpeedRpm(
        wheel, applied_drive_velocity[wheel], &forward);
    if (!MWRS_Drivers_SetDrive(wheel, drive_rpm, forward))
    {
      driver_status[wheel].drive_online = false;
      return false;
    }
  }
  outputs_active = true;
  return true;
#endif
}

static void execute_command(const MwrsWheelCommand *command)
{
  uint32_t now = HAL_GetTick();
  last_valid_command_ms = now;
  last_sequence_id = command->sequence_id;
  command_timeout = false;
  software_estop = command->estop;
  protocol_fault_code = MWRS_FAULT_NONE;

  if (command->estop)
  {
    stop_outputs(true, true);
    send_ack(command->sequence_id, true, MWRS_FAULT_NONE);
    return;
  }
  if (!command->enabled || command->mode == 0U)
  {
    stop_outputs(false, false);
    send_ack(command->sequence_id, true, MWRS_FAULT_NONE);
    return;
  }
  if (!command_uses_configured_wheels(command))
  {
    stop_outputs(true, true);
    send_ack(command->sequence_id, false, MWRS_FAULT_RANGE);
    return;
  }

  poll_driver_health(false);
  uint32_t fault = effective_fault_code();
  if (!drivers_ready() || fault != MWRS_FAULT_NONE)
  {
    stop_outputs(true, true);
    send_ack(
        command->sequence_id,
        false,
        fault != MWRS_FAULT_NONE ? fault : MWRS_FAULT_HOMING);
    return;
  }
  if (!apply_motion_command(command))
  {
    stop_outputs(true, true);
    fault = effective_fault_code();
    send_ack(
        command->sequence_id,
        false,
        fault != MWRS_FAULT_NONE ? fault : MWRS_FAULT_STEERING_BASE);
    return;
  }
  send_ack(command->sequence_id, true, MWRS_FAULT_NONE);
}

static void handle_frame(const char *frame, size_t frame_length)
{
  MwrsWheelCommand command;
  MwrsProtocolParseResult result = MWRS_Protocol_ParseWheelFrame(
      frame, frame_length, &command);
  if (!result.valid)
  {
    protocol_fault_code = result.fault_code;
    stop_outputs(true, false);
    if (result.sequence_trusted)
    {
      send_ack(command.sequence_id, false, result.fault_code);
    }
    return;
  }
  execute_command(&command);
}

static bool ring_pop(uint8_t *value)
{
  if (pi_rx_tail == pi_rx_head)
  {
    return false;
  }
  *value = pi_rx_ring[pi_rx_tail];
  pi_rx_tail = (uint16_t)((pi_rx_tail + 1U) % PI_RX_RING_BYTES);
  return true;
}

static void poll_pi_uart(void)
{
  if (pi_rx_overflow)
  {
    pi_rx_overflow = false;
    rx_frame_length = 0U;
    discard_until_newline = true;
    protocol_fault_code = MWRS_FAULT_FRAME_OVERFLOW;
    stop_outputs(true, false);
  }

  uint8_t byte = 0U;
  while (ring_pop(&byte))
  {
    if (discard_until_newline)
    {
      if (byte == '\n')
      {
        discard_until_newline = false;
      }
      continue;
    }
    if (byte == '\r')
    {
      continue;
    }
    if (byte == '\n')
    {
      if (rx_frame_length > 0U)
      {
        rx_frame[rx_frame_length] = '\0';
        handle_frame(rx_frame, rx_frame_length);
        rx_frame_length = 0U;
      }
      continue;
    }
    if (rx_frame_length >= MWRS_MAX_FRAME_BYTES - 1U)
    {
      rx_frame_length = 0U;
      discard_until_newline = true;
      protocol_fault_code = MWRS_FAULT_FRAME_OVERFLOW;
      stop_outputs(true, false);
      continue;
    }
    rx_frame[rx_frame_length++] = (char)byte;
  }
}

static void poll_safety(void)
{
  uint32_t now = HAL_GetTick();
  if (hardware_estop_active())
  {
    stop_outputs(true, false);
  }
  if (!command_timeout && now - last_valid_command_ms > MWRS_PI_COMMAND_TIMEOUT_MS)
  {
    command_timeout = true;
    stop_outputs(true, true);
  }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart)
{
  if (uart == &PI_UART)
  {
    uint16_t next = (uint16_t)((pi_rx_head + 1U) % PI_RX_RING_BYTES);
    if (next == pi_rx_tail)
    {
      pi_rx_overflow = true;
    }
    else
    {
      pi_rx_ring[pi_rx_head] = pi_rx_byte;
      pi_rx_head = next;
    }
    (void)HAL_UART_Receive_IT(&PI_UART, (uint8_t *)&pi_rx_byte, 1U);
  }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
  if (uart == &PI_UART)
  {
    pi_rx_overflow = true;
    (void)HAL_UART_AbortReceive(&PI_UART);
    (void)HAL_UART_Receive_IT(&PI_UART, (uint8_t *)&pi_rx_byte, 1U);
  }
}

void MWRS_Control_Init(void)
{
  memset(driver_status, 0, sizeof(driver_status));
  memset(applied_drive_velocity, 0, sizeof(applied_drive_velocity));
  memset(wheel_output_active, 0, sizeof(wheel_output_active));
  pi_rx_head = 0U;
  pi_rx_tail = 0U;
  pi_rx_overflow = false;
  rx_frame_length = 0U;
  discard_until_newline = false;

  uint32_t now = HAL_GetTick();
  last_valid_command_ms = now;
  last_status_ms = now - MWRS_STATUS_PERIOD_MS;
  last_health_poll_ms = now - MWRS_DRIVER_HEALTH_PERIOD_MS;
  last_execution_ms = now;
  last_sequence_id = 0U;
  command_timeout = true;
  software_estop = false;
  outputs_active = false;
  protocol_fault_code = MWRS_FAULT_NONE;

  MWRS_Drivers_Init();
  (void)HAL_UART_Receive_IT(&PI_UART, (uint8_t *)&pi_rx_byte, 1U);
  stop_outputs(true, true);
  poll_driver_health(true);
  send_status();
  last_status_ms = HAL_GetTick();
}

void MWRS_Control_Process(void)
{
  poll_pi_uart();
  poll_safety();
  poll_driver_health(false);

  uint32_t now = HAL_GetTick();
  if (now - last_status_ms >= MWRS_STATUS_PERIOD_MS)
  {
    send_status();
    last_status_ms = now;
  }
}
