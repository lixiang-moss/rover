### ESP32 Motor Control Demo

This Arduino sketch demonstrates controlling **one MKS SERVO57D stepper** and **one BLD-405S BLDC driver** using the ESP32’s GPIO pins:

- **Stepper** (PUL/DIR/ENA mode): step pulses on `GPIO16`, direction on `GPIO17`, enable on `GPIO4`.
- **BLDC** (analog/PWM mode): speed via PWM on `GPIO5` (VSP input), direction on `GPIO18`, enable on `GPIO19`.
- Both drivers share **GND** with the ESP32 and have independent 24 V power supplies.
- PWM is generated with the ESP32 `ledc` hardware for smooth speed control.

The code is intended for quick bench testing and does not use RS-485; all control is via the drivers’ discrete input pins.

PS: 4 Stepper 2 DC was not tested because of the missing of the power supply

## **main.c code for the STM32 with using the Modbus**

## flask_code.py code RPi for the APP 

## cmd_publisher_node ROS2 node for the RPi 