#ifndef MWRS_CONTROL_H
#define MWRS_CONTROL_H

#include "main.h"

#include <stdbool.h>

void MWRS_Control_Init(void);
void MWRS_Control_Process(void);

/*
 * The hardware owner must override this weak function and set
 * MWRS_HARDWARE_ESTOP_CONFIGURED=1 before enabling real actuation.
 */
bool MWRS_HardwareEstopActive(void);

#endif
