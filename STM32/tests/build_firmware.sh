#!/usr/bin/env bash
set -euo pipefail

stm32_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
build_dir="${stm32_dir}/tests/build/arm"
mkdir -p "${build_dir}"

common_flags=(
  -mcpu=cortex-m4
  -mthumb
  -mfpu=fpv4-sp-d16
  -mfloat-abi=hard
  -std=gnu11
  -DUSE_HAL_DRIVER
  -DSTM32G474xx
  -I"${stm32_dir}/Core/Inc"
  -I"${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Inc"
  -I"${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Inc/Legacy"
  -I"${stm32_dir}/Drivers/CMSIS/Device/ST/STM32G4xx/Include"
  -I"${stm32_dir}/Drivers/CMSIS/Include"
  -O0
  -g3
  -ffunction-sections
  -fdata-sections
  -Wall
  -Wextra
)

sources=(
  "${stm32_dir}/Core/Src/cJSON.c"
  "${stm32_dir}/Core/Src/main.c"
  "${stm32_dir}/Core/Src/mwrs_control.c"
  "${stm32_dir}/Core/Src/mwrs_drivers.c"
  "${stm32_dir}/Core/Src/mwrs_modbus.c"
  "${stm32_dir}/Core/Src/mwrs_protocol.c"
  "${stm32_dir}/Core/Src/mwrs_units.c"
  "${stm32_dir}/Core/Src/stm32g4xx_hal_msp.c"
  "${stm32_dir}/Core/Src/stm32g4xx_it.c"
  "${stm32_dir}/Core/Src/syscalls.c"
  "${stm32_dir}/Core/Src/sysmem.c"
  "${stm32_dir}/Core/Src/system_stm32g4xx.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_cortex.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_dma.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_dma_ex.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_exti.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_flash.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_flash_ex.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_flash_ramfunc.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_gpio.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_pwr.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_pwr_ex.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_rcc.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_rcc_ex.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_uart.c"
  "${stm32_dir}/Drivers/STM32G4xx_HAL_Driver/Src/stm32g4xx_hal_uart_ex.c"
)

objects=()
for source in "${sources[@]}"; do
  object="${build_dir}/$(basename "${source%.c}").o"
  arm-none-eabi-gcc "${common_flags[@]}" -c "${source}" -o "${object}"
  objects+=("${object}")
done

startup_object="${build_dir}/startup_stm32g474retx.o"
arm-none-eabi-gcc \
  -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard \
  -c "${stm32_dir}/Core/Startup/startup_stm32g474retx.s" \
  -o "${startup_object}"
objects+=("${startup_object}")

elf="${build_dir}/mars_rover_stm32.elf"
arm-none-eabi-gcc \
  -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard \
  -T"${stm32_dir}/STM32G474RETX_FLASH.ld" \
  --specs=nosys.specs --specs=nano.specs \
  -Wl,-Map="${build_dir}/mars_rover_stm32.map" \
  -Wl,--gc-sections -static \
  "${objects[@]}" \
  -Wl,--start-group -lc -lm -Wl,--end-group \
  -o "${elf}"

arm-none-eabi-size "${elf}"
