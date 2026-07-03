#include "mwrs_modbus.h"

#include <string.h>

#define MODBUS_MAX_FRAME_BYTES 64U

static uint16_t modbus_crc16(const uint8_t *data, uint16_t length)
{
  uint16_t crc = 0xFFFFU;
  for (uint16_t index = 0U; index < length; index++)
  {
    crc ^= data[index];
    for (uint8_t bit = 0U; bit < 8U; bit++)
    {
      crc = (crc & 1U) != 0U ? (uint16_t)((crc >> 1) ^ 0xA001U) : (uint16_t)(crc >> 1);
    }
  }
  return crc;
}

static void flush_receive_buffer(UART_HandleTypeDef *uart)
{
  uint8_t discarded = 0U;
  while (HAL_UART_Receive(uart, &discarded, 1U, 0U) == HAL_OK)
  {
  }
  __HAL_UART_CLEAR_OREFLAG(uart);
}

static bool transmit_request(
    const MwrsModbusBus *bus,
    const uint8_t *request,
    uint16_t request_length)
{
  flush_receive_buffer(bus->uart);
  HAL_GPIO_WritePin(bus->direction_port, bus->direction_pin, GPIO_PIN_SET);
  for (volatile uint32_t delay = 0U; delay < 250U; delay++)
  {
  }

  HAL_StatusTypeDef status = HAL_UART_Transmit(
      bus->uart, (uint8_t *)request, request_length, bus->timeout_ms);
  if (status == HAL_OK)
  {
    uint32_t started = HAL_GetTick();
    while (__HAL_UART_GET_FLAG(bus->uart, UART_FLAG_TC) == RESET)
    {
      if (HAL_GetTick() - started >= bus->timeout_ms)
      {
        status = HAL_TIMEOUT;
        break;
      }
    }
  }

  for (volatile uint32_t delay = 0U; delay < 250U; delay++)
  {
  }
  HAL_GPIO_WritePin(bus->direction_port, bus->direction_pin, GPIO_PIN_RESET);
  return status == HAL_OK;
}

static bool receive_response(
    const MwrsModbusBus *bus,
    uint8_t slave,
    uint8_t function_code,
    uint8_t *response,
    uint16_t *response_length)
{
  if (HAL_UART_Receive(bus->uart, response, 3U, bus->timeout_ms) != HAL_OK)
  {
    return false;
  }

  uint16_t total_length = 0U;
  if (response[1] == (uint8_t)(function_code | 0x80U))
  {
    total_length = 5U;
  }
  else if (response[1] != function_code)
  {
    return false;
  }
  else if (function_code == 0x03U || function_code == 0x04U)
  {
    total_length = (uint16_t)(response[2] + 5U);
  }
  else
  {
    total_length = 8U;
  }

  if (response[0] != slave || total_length < 5U || total_length > MODBUS_MAX_FRAME_BYTES)
  {
    return false;
  }
  if (HAL_UART_Receive(
          bus->uart,
          &response[3],
          (uint16_t)(total_length - 3U),
          bus->timeout_ms) != HAL_OK)
  {
    return false;
  }

  uint16_t received_crc = (uint16_t)response[total_length - 2U] |
                          (uint16_t)((uint16_t)response[total_length - 1U] << 8);
  if (received_crc != modbus_crc16(response, (uint16_t)(total_length - 2U)) ||
      response[1] == (uint8_t)(function_code | 0x80U))
  {
    return false;
  }
  *response_length = total_length;
  return true;
}

static bool exchange(
    const MwrsModbusBus *bus,
    uint8_t slave,
    uint8_t function_code,
    uint8_t *request,
    uint16_t request_length,
    uint8_t *response,
    uint16_t *response_length)
{
  if (bus == NULL || bus->uart == NULL || request == NULL || response == NULL ||
      response_length == NULL || request_length < 4U || request_length > MODBUS_MAX_FRAME_BYTES)
  {
    return false;
  }
  uint16_t crc = modbus_crc16(request, (uint16_t)(request_length - 2U));
  request[request_length - 2U] = (uint8_t)(crc & 0xFFU);
  request[request_length - 1U] = (uint8_t)(crc >> 8);
  return transmit_request(bus, request, request_length) &&
         receive_response(bus, slave, function_code, response, response_length);
}

bool MWRS_Modbus_WriteSingle(
    const MwrsModbusBus *bus,
    uint8_t slave,
    uint16_t register_address,
    uint16_t value)
{
  uint8_t request[8] = {
      slave,
      0x06U,
      (uint8_t)(register_address >> 8),
      (uint8_t)register_address,
      (uint8_t)(value >> 8),
      (uint8_t)value,
      0U,
      0U};
  uint8_t response[MODBUS_MAX_FRAME_BYTES];
  uint16_t response_length = 0U;
  return exchange(
             bus, slave, 0x06U, request, sizeof(request), response, &response_length) &&
         response_length == sizeof(request) &&
         memcmp(request, response, 6U) == 0;
}

bool MWRS_Modbus_WriteMultiple(
    const MwrsModbusBus *bus,
    uint8_t slave,
    uint16_t register_address,
    const uint8_t *data,
    uint8_t data_length)
{
  if (data == NULL || data_length == 0U || (data_length & 1U) != 0U || data_length > 32U)
  {
    return false;
  }
  uint16_t register_count = (uint16_t)(data_length / 2U);
  uint16_t request_length = (uint16_t)(9U + data_length);
  uint8_t request[MODBUS_MAX_FRAME_BYTES] = {0U};
  request[0] = slave;
  request[1] = 0x10U;
  request[2] = (uint8_t)(register_address >> 8);
  request[3] = (uint8_t)register_address;
  request[4] = (uint8_t)(register_count >> 8);
  request[5] = (uint8_t)register_count;
  request[6] = data_length;
  memcpy(&request[7], data, data_length);

  uint8_t response[MODBUS_MAX_FRAME_BYTES];
  uint16_t response_length = 0U;
  return exchange(
             bus, slave, 0x10U, request, request_length, response, &response_length) &&
         response_length == 8U &&
         response[2] == request[2] && response[3] == request[3] &&
         response[4] == request[4] && response[5] == request[5];
}

bool MWRS_Modbus_ReadRegisters(
    const MwrsModbusBus *bus,
    uint8_t slave,
    uint8_t function_code,
    uint16_t register_address,
    uint16_t register_count,
    uint8_t *data,
    size_t data_size)
{
  if ((function_code != 0x03U && function_code != 0x04U) ||
      register_count == 0U || register_count > 16U || data == NULL ||
      data_size < (size_t)register_count * 2U)
  {
    return false;
  }
  uint8_t request[8] = {
      slave,
      function_code,
      (uint8_t)(register_address >> 8),
      (uint8_t)register_address,
      (uint8_t)(register_count >> 8),
      (uint8_t)register_count,
      0U,
      0U};
  uint8_t response[MODBUS_MAX_FRAME_BYTES];
  uint16_t response_length = 0U;
  uint8_t expected_bytes = (uint8_t)(register_count * 2U);
  if (!exchange(
          bus,
          slave,
          function_code,
          request,
          sizeof(request),
          response,
          &response_length) ||
      response_length != (uint16_t)(expected_bytes + 5U) ||
      response[2] != expected_bytes)
  {
    return false;
  }
  memcpy(data, &response[3], expected_bytes);
  return true;
}
