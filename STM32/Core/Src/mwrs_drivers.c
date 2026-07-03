#include "mwrs_drivers.h"

#include "main.h"
#include "mwrs_modbus.h"

#include <stdlib.h>
#include <string.h>

extern UART_HandleTypeDef huart1;
extern UART_HandleTypeDef huart3;

#define MKS_REG_HOMING_STATUS        0x003BU
#define MKS_REG_STALL_STATUS         0x003EU
#define MKS_REG_COORDINATE           0x0031U
#define MKS_REG_ENABLE               0x00F3U
#define MKS_REG_EMERGENCY_STOP       0x00F7U
#define MKS_REG_ABSOLUTE_COORDINATE  0x00F5U

#define BLD_REG_SPEED_RPM            0x0056U
#define BLD_REG_ACTUAL_SPEED_RPM     0x005FU
#define BLD_REG_RUN_STATE            0x0066U
#define BLD_REG_FAULT                0x0076U

#define BLD_STATE_STOP               0U
#define BLD_STATE_FORWARD            1U
#define BLD_STATE_REVERSE            2U
#define BLD_STATE_BRAKE              3U

static const uint8_t mks_ids[MWRS_WHEEL_COUNT] = MWRS_MKS_IDS;
static const uint8_t bld_ids[MWRS_WHEEL_COUNT] = MWRS_BLD_IDS;

static MwrsModbusBus mks_bus;
static MwrsModbusBus bld_bus;
static bool mks_enabled[MWRS_WHEEL_COUNT];
static bool mks_target_valid[MWRS_WHEEL_COUNT];
static int32_t mks_target_coordinate[MWRS_WHEEL_COUNT];
static uint16_t mks_target_speed_rpm[MWRS_WHEEL_COUNT];
static uint8_t bld_run_state[MWRS_WHEEL_COUNT];
static uint16_t bld_speed_rpm[MWRS_WHEEL_COUNT];

static int64_t signed_int48(const uint8_t data[6])
{
  uint64_t value = 0U;
  for (uint8_t index = 0U; index < 6U; index++)
  {
    value = (value << 8) | data[index];
  }
  if ((value & (1ULL << 47)) != 0ULL)
  {
    value |= 0xFFFF000000000000ULL;
  }
  return (int64_t)value;
}

void MWRS_Drivers_Init(void)
{
  mks_bus.uart = &huart1;
  mks_bus.direction_port = RS485_DIR1_GPIO_Port;
  mks_bus.direction_pin = RS485_DIR1_Pin;
  mks_bus.timeout_ms = MWRS_MODBUS_TIMEOUT_MS;

  bld_bus.uart = &huart3;
  bld_bus.direction_port = RS485_DIR2_GPIO_Port;
  bld_bus.direction_pin = RS485_DIR2_Pin;
  bld_bus.timeout_ms = MWRS_MODBUS_TIMEOUT_MS;

  memset(mks_enabled, 0, sizeof(mks_enabled));
  memset(mks_target_valid, 0, sizeof(mks_target_valid));
  memset(mks_target_coordinate, 0, sizeof(mks_target_coordinate));
  memset(mks_target_speed_rpm, 0, sizeof(mks_target_speed_rpm));
  memset(bld_run_state, 0, sizeof(bld_run_state));
  memset(bld_speed_rpm, 0, sizeof(bld_speed_rpm));
  HAL_GPIO_WritePin(RS485_DIR1_GPIO_Port, RS485_DIR1_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(RS485_DIR2_GPIO_Port, RS485_DIR2_Pin, GPIO_PIN_RESET);
}

bool MWRS_Drivers_ReadSteeringCoordinate(uint8_t wheel, int64_t *coordinate)
{
  if (wheel >= MWRS_WHEEL_COUNT || coordinate == NULL)
  {
    return false;
  }
  uint8_t data[6];
  if (!MWRS_Modbus_ReadRegisters(
          &mks_bus, mks_ids[wheel], 0x04U, MKS_REG_COORDINATE, 3U, data, sizeof(data)))
  {
    return false;
  }
  *coordinate = signed_int48(data);
  return true;
}

bool MWRS_Drivers_ReadStatus(uint8_t wheel, MwrsDriverStatus *status)
{
  if (wheel >= MWRS_WHEEL_COUNT || status == NULL)
  {
    return false;
  }
  memset(status, 0, sizeof(*status));

  uint8_t homing[2];
  uint8_t stalled[2];
  bool homing_ok = MWRS_Modbus_ReadRegisters(
      &mks_bus, mks_ids[wheel], 0x04U, MKS_REG_HOMING_STATUS, 1U, homing, sizeof(homing));
  bool stall_ok = MWRS_Modbus_ReadRegisters(
      &mks_bus, mks_ids[wheel], 0x04U, MKS_REG_STALL_STATUS, 1U, stalled, sizeof(stalled));
  bool coordinate_ok = MWRS_Drivers_ReadSteeringCoordinate(wheel, &status->steering_coordinate);
  status->steering_online = homing_ok && stall_ok && coordinate_ok;
  status->homed = homing_ok && homing[1] == 1U;
  status->steering_fault = !status->steering_online || (stall_ok && stalled[1] != 0U);

  uint8_t bld_speed[2];
  uint8_t bld_run[2];
  uint8_t bld_fault[2];
  bool bld_speed_ok = MWRS_Modbus_ReadRegisters(
      &bld_bus, bld_ids[wheel], 0x03U, BLD_REG_ACTUAL_SPEED_RPM, 1U,
      bld_speed, sizeof(bld_speed));
  bool bld_run_ok = MWRS_Modbus_ReadRegisters(
      &bld_bus, bld_ids[wheel], 0x03U, BLD_REG_RUN_STATE, 1U,
      bld_run, sizeof(bld_run));
  bool bld_fault_ok = MWRS_Modbus_ReadRegisters(
      &bld_bus, bld_ids[wheel], 0x03U, BLD_REG_FAULT, 1U, bld_fault, sizeof(bld_fault));
  status->drive_online = bld_speed_ok && bld_run_ok && bld_fault_ok;
  if (status->drive_online)
  {
    status->drive_speed_rpm = (uint16_t)((uint16_t)bld_speed[0] << 8) | bld_speed[1];
    status->drive_run_state = (uint16_t)((uint16_t)bld_run[0] << 8) | bld_run[1];
    status->drive_fault_raw = (uint16_t)((uint16_t)bld_fault[0] << 8) | bld_fault[1];
  }
  status->drive_fault = !status->drive_online || status->drive_fault_raw != 0U;
  return status->steering_online && status->drive_online;
}

bool MWRS_Drivers_SetSteering(
    uint8_t wheel,
    int32_t target_coordinate,
    uint16_t speed_rpm)
{
  if (wheel >= MWRS_WHEEL_COUNT || speed_rpm > MWRS_MKS_MAX_SPEED_RPM)
  {
    return false;
  }
  if (!mks_enabled[wheel])
  {
    if (!MWRS_Modbus_WriteSingle(&mks_bus, mks_ids[wheel], MKS_REG_ENABLE, 1U))
    {
      return false;
    }
    mks_enabled[wheel] = true;
  }
  if (mks_target_valid[wheel] &&
      mks_target_coordinate[wheel] == target_coordinate &&
      mks_target_speed_rpm[wheel] == speed_rpm)
  {
    return true;
  }

  uint32_t coordinate_bits = (uint32_t)target_coordinate;
  uint8_t data[8] = {
      0U,
      (uint8_t)MWRS_MKS_POSITION_ACCELERATION,
      (uint8_t)(speed_rpm >> 8),
      (uint8_t)speed_rpm,
      (uint8_t)(coordinate_bits >> 24),
      (uint8_t)(coordinate_bits >> 16),
      (uint8_t)(coordinate_bits >> 8),
      (uint8_t)coordinate_bits};
  if (!MWRS_Modbus_WriteMultiple(
          &mks_bus, mks_ids[wheel], MKS_REG_ABSOLUTE_COORDINATE, data, sizeof(data)))
  {
    return false;
  }
  mks_target_valid[wheel] = true;
  mks_target_coordinate[wheel] = target_coordinate;
  mks_target_speed_rpm[wheel] = speed_rpm;
  return true;
}

bool MWRS_Drivers_SetDrive(uint8_t wheel, uint16_t speed_rpm, bool forward)
{
  if (wheel >= MWRS_WHEEL_COUNT || speed_rpm > MWRS_BLD_MAX_SPEED_RPM)
  {
    return false;
  }
  if (speed_rpm == 0U)
  {
    if (bld_run_state[wheel] == BLD_STATE_STOP && bld_speed_rpm[wheel] == 0U)
    {
      return true;
    }
    return MWRS_Drivers_StopDrive(wheel, false);
  }

  uint8_t desired_state = forward ? BLD_STATE_FORWARD : BLD_STATE_REVERSE;
  if (bld_run_state[wheel] == desired_state && bld_speed_rpm[wheel] == speed_rpm)
  {
    return true;
  }
  if (bld_run_state[wheel] != BLD_STATE_STOP && bld_run_state[wheel] != desired_state)
  {
    if (!MWRS_Modbus_WriteSingle(
            &bld_bus, bld_ids[wheel], BLD_REG_RUN_STATE, BLD_STATE_STOP))
    {
      return false;
    }
    bld_run_state[wheel] = BLD_STATE_STOP;
    bld_speed_rpm[wheel] = 0U;
  }
  if (!MWRS_Modbus_WriteSingle(
          &bld_bus, bld_ids[wheel], BLD_REG_SPEED_RPM, speed_rpm) ||
      !MWRS_Modbus_WriteSingle(
          &bld_bus, bld_ids[wheel], BLD_REG_RUN_STATE, desired_state))
  {
    (void)MWRS_Modbus_WriteSingle(
        &bld_bus, bld_ids[wheel], BLD_REG_RUN_STATE, BLD_STATE_STOP);
    bld_run_state[wheel] = BLD_STATE_STOP;
    bld_speed_rpm[wheel] = 0U;
    return false;
  }
  bld_run_state[wheel] = desired_state;
  bld_speed_rpm[wheel] = speed_rpm;
  return true;
}

bool MWRS_Drivers_StopDrive(uint8_t wheel, bool brake)
{
  if (wheel >= MWRS_WHEEL_COUNT)
  {
    return false;
  }
  uint16_t stop_state = brake ? BLD_STATE_BRAKE : BLD_STATE_STOP;
  bool state_ok = MWRS_Modbus_WriteSingle(
      &bld_bus, bld_ids[wheel], BLD_REG_RUN_STATE, stop_state);
  bool speed_ok = MWRS_Modbus_WriteSingle(
      &bld_bus, bld_ids[wheel], BLD_REG_SPEED_RPM, 0U);
  bld_run_state[wheel] = BLD_STATE_STOP;
  bld_speed_rpm[wheel] = 0U;
  return state_ok && speed_ok;
}

bool MWRS_Drivers_StopWheel(uint8_t wheel, bool emergency)
{
  if (wheel >= MWRS_WHEEL_COUNT)
  {
    return false;
  }
  bool mks_ok = MWRS_Modbus_WriteSingle(
      &mks_bus, mks_ids[wheel], MKS_REG_EMERGENCY_STOP, 1U);
  mks_enabled[wheel] = false;
  mks_target_valid[wheel] = false;
  return mks_ok && MWRS_Drivers_StopDrive(wheel, emergency);
}

bool MWRS_Drivers_StopAll(uint8_t wheel_count, bool emergency)
{
  bool all_ok = true;
  if (wheel_count > MWRS_WHEEL_COUNT)
  {
    wheel_count = MWRS_WHEEL_COUNT;
  }
  for (uint8_t wheel = 0U; wheel < wheel_count; wheel++)
  {
    if (!MWRS_Drivers_StopWheel(wheel, emergency))
    {
      all_ok = false;
    }
  }
  return all_ok;
}
