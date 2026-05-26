#include "main.h"
#include <string.h>
#include <stdarg.h>
#include <stdio.h>

/* ================== Pin/UART wiring ================== */
// TODO: change these to match your CubeMX config
extern UART_HandleTypeDef huart2; // RS-485 A: Stepper (SERVO57D)
extern UART_HandleTypeDef huart3; // RS-485 B: BLDC (BLD-405S)

#define RS485A_DE_GPIO_Port   GPIOA     // TODO
#define RS485A_DE_Pin         GPIO_PIN_5// TODO (DE/RE tied)

#define RS485B_DE_GPIO_Port   GPIOB     // TODO
#define RS485B_DE_Pin         GPIO_PIN_1// TODO

/* ================== Helpers ================== */
static void rs485_tx(UART_HandleTypeDef *huart, GPIO_TypeDef* de_port, uint16_t de_pin,
                     const uint8_t *buf, uint16_t len)
{
    HAL_GPIO_WritePin(de_port, de_pin, GPIO_PIN_SET);
    HAL_UART_Transmit(huart, (uint8_t*)buf, len, 100);
    // wait for TC so DE drops only after last bit
    while (__HAL_UART_GET_FLAG(huart, UART_FLAG_TC) == RESET) {}
    HAL_GPIO_WritePin(de_port, de_pin, GPIO_PIN_RESET);
}

static uint16_t modbus_crc16(const uint8_t *buf, uint16_t len)
{
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < len; i++) {
        crc ^= buf[i];
        for (uint8_t j = 0; j < 8; j++)
            crc = (crc & 1) ? (crc >> 1) ^ 0xA001 : (crc >> 1);
    }
    return crc;
}

/* ================== BLD-405S (BLDC) ================== */
// Registers per StepperOnline BLD family docs.
// 0x8000: [high byte]=control bits; [low byte]=pole pairs
// 0x8005: target speed (RPM); 0x8018: actual speed (read-only).
// 8-N-1 @ 57600 bps. Function 0x06 for write, 0x03 for read.

static void bld_write_reg(uint8_t slave, uint16_t reg, uint16_t value)
{
    uint8_t pdu[8];
    pdu[0] = slave;
    pdu[1] = 0x06;
    pdu[2] = (uint8_t)(reg >> 8);
    pdu[3] = (uint8_t)(reg & 0xFF);
    pdu[4] = (uint8_t)(value >> 8);
    pdu[5] = (uint8_t)(value & 0xFF);
    uint16_t crc = modbus_crc16(pdu, 6);
    pdu[6] = (uint8_t)(crc & 0xFF);
    pdu[7] = (uint8_t)(crc >> 8);
    rs485_tx(&huart3, RS485B_DE_GPIO_Port, RS485B_DE_Pin, pdu, sizeof pdu);
}

static void bld_start(uint8_t slave, uint8_t dir_cw, uint8_t pole_pairs)
{
    // Control byte patterns seen in BLD manuals:
    // 0x19 = EN=1,NW=1,MDX=1,FR=0 ; 0x1B = same + FR=1 (CCW)
    uint8_t ctrl_hi = dir_cw ? 0x19 : 0x1B;
    uint16_t word = ((uint16_t)ctrl_hi << 8) | (uint16_t)pole_pairs;
    bld_write_reg(slave, 0x8000, word);
}

static void bld_stop(uint8_t slave, uint8_t pole_pairs, uint8_t brake)
{
    uint8_t ctrl_hi = brake ? 0x0D : 0x08; // 0x08 natural stop, 0x0D brake stop
    uint16_t word = ((uint16_t)ctrl_hi << 8) | (uint16_t)pole_pairs;
    bld_write_reg(slave, 0x8000, word);
}

static void bld_set_speed_rpm(uint8_t slave, uint16_t rpm)
{
    bld_write_reg(slave, 0x8005, rpm);
}

/* ================== MKS SERVO57D (stepper) ==================
   Speed mode = Function 0x10 to 0x00F6, Qty=2 regs, 4 data bytes:
   [dir (1B), acc (1B), speed_rpm (Hi,Lo)].
   Stop: same write with speed=0; acc=0 => immediate stop. */

static void mks_write_single(uint8_t slave, uint16_t reg, uint16_t value)
{
    uint8_t pdu[8];
    pdu[0] = slave;
    pdu[1] = 0x06;
    pdu[2] = (uint8_t)(reg >> 8);
    pdu[3] = (uint8_t)(reg & 0xFF);
    pdu[4] = (uint8_t)(value >> 8);
    pdu[5] = (uint8_t)(value & 0xFF);
    uint16_t crc = modbus_crc16(pdu, 6);
    pdu[6] = (uint8_t)(crc & 0xFF);
    pdu[7] = (uint8_t)(crc >> 8);
    rs485_tx(&huart2, RS485A_DE_GPIO_Port, RS485A_DE_Pin, pdu, sizeof pdu);
}

static void mks_speed_run(uint8_t slave, uint8_t dir_cw, uint8_t acc_0_255, uint16_t rpm_0_3000)
{
    uint8_t pdu[13];
    pdu[0]  = slave;
    pdu[1]  = 0x10;           // Write Multiple Registers
    pdu[2]  = 0x00; pdu[3] = 0xF6;  // start address
    pdu[4]  = 0x00; pdu[5] = 0x02;  // quantity=2 regs (4 bytes)
    pdu[6]  = 0x04;                // byte count
    pdu[7]  = dir_cw ? 0x01 : 0x00; // dir: 0/1 per manual note (CW/CCW)
    pdu[8]  = acc_0_255;           // acceleration 0..255
    pdu[9]  = (uint8_t)(rpm_0_3000 >> 8);
    pdu[10] = (uint8_t)(rpm_0_3000 & 0xFF);
    uint16_t crc = modbus_crc16(pdu, 11);
    pdu[11] = (uint8_t)(crc & 0xFF);
    pdu[12] = (uint8_t)(crc >> 8);
    rs485_tx(&huart2, RS485A_DE_GPIO_Port, RS485A_DE_Pin, pdu, sizeof pdu);
}

static void mks_speed_stop(uint8_t slave, uint8_t immediate)
{
    // acc=0 => immediate stop; acc!=0 => ramp down
    uint8_t acc = immediate ? 0 : 50; // pick a gentle decel if not immediate
    mks_speed_run(slave, 1, acc, 0);
}

// Optional: set baud to 57600 and enable Modbus RTU on SERVO57D
static void mks_enable_modbus_and_set_baud57600(uint8_t slave)
{
    mks_write_single(slave, 0x008E, 0x0001); // MB_RTU enable
    mks_write_single(slave, 0x008A, 0x0005); // baud=57600
}

/* ================== Demo ================== */

static void motors_demo(void)
{
    // ======== CONFIGURE UARTS IN CUBEMX ========
    // huart3 (BLD-405S): 57600, 8N1
    // huart2 (SERVO57D): match your motor’s setting (e.g., 57600 8N1)
    // You can push SERVO57D to 57600 via the helper above.

    const uint8_t BLD_ID = 0x01;   
    const uint8_t MKS_ID = 0x05; 
    const uint8_t POLE_PAIRS = 0x03; // example: 3PP BLDC motor

    HAL_Delay(200);

    // (Optional) Make SERVO57D speak Modbus RTU @57600:
    // mks_enable_modbus_and_set_baud57600(MKS_ID);
    HAL_Delay(50);

    // Start BLDC CW at 600 RPM; you must start (EN) before/after writing speed
    bld_set_speed_rpm(BLD_ID, 600);
    HAL_Delay(10);
    bld_start(BLD_ID, /*dir_cw=*/1, POLE_PAIRS);

    // Start stepper CW at 300 RPM with moderate accel
    mks_speed_run(MKS_ID, /*dir_cw=*/1, /*acc*/80, /*rpm*/300);

    HAL_Delay(3000);

    // Change directions/speeds to prove control
    bld_set_speed_rpm(BLD_ID, 900);
    mks_speed_run(MKS_ID, /*dir_cw=*/0, /*acc*/80, /*rpm*/250);

    HAL_Delay(3000);

    // Stop both (natural stop BLDC; immediate stop stepper)
    bld_stop(BLD_ID, POLE_PAIRS, /*brake=*/0);
    mks_speed_stop(MKS_ID, /*immediate=*/1);
}

/* ================== main() hook ================== */
int main(void)
{
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_USART2_UART_Init();
    MX_USART3_UART_Init();

    // Ensure DE pins start low (receive mode)
    HAL_GPIO_WritePin(RS485A_DE_GPIO_Port, RS485A_DE_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(RS485B_DE_GPIO_Port, RS485B_DE_Pin, GPIO_PIN_RESET);

    motors_demo();

    while (1) {
        HAL_Delay(1000);
    }
}
