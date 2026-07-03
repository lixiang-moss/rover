#ifndef MWRS_MODBUS_H
#define MWRS_MODBUS_H

#include "main.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct
{
  UART_HandleTypeDef *uart;
  GPIO_TypeDef *direction_port;
  uint16_t direction_pin;
  uint32_t timeout_ms;
} MwrsModbusBus;

bool MWRS_Modbus_WriteSingle(
    const MwrsModbusBus *bus,
    uint8_t slave,
    uint16_t register_address,
    uint16_t value);

bool MWRS_Modbus_WriteMultiple(
    const MwrsModbusBus *bus,
    uint8_t slave,
    uint16_t register_address,
    const uint8_t *data,
    uint8_t data_length);

bool MWRS_Modbus_ReadRegisters(
    const MwrsModbusBus *bus,
    uint8_t slave,
    uint8_t function_code,
    uint16_t register_address,
    uint16_t register_count,
    uint8_t *data,
    size_t data_size);

#endif
