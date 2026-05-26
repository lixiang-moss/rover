#include <Arduino.h>
#include <math.h>

// —————————————————————
// Pin Definitions (per wheel)
// —————————————————————
// Stepper pins
const int STEP_PINS[4] = {16, 21, 23, 25};
const int DIR_PINS[4]  = {17, 22, 24, 26};
const int EN_PINS[4]   = {4,  27, 32, 33};  // active LOW
// DC pins (front and rear only)
const int PWM_PINS[2]  = {5, 12};
const int DIR_D_PINS[2] = {18, 14};
const int EN_D_PINS[2]  = {19, 13}; // active LOW

// —————————————————————
// Geometry & Motor Constants
// —————————————————————
const float TRACK_WIDTH_M     = 0.40f;
const float WHEEL_BASE_M      = 0.70f;
const float WHEEL_RADIUS_M    = 0.10f;

const uint32_t MOTOR_FULL_STEPS_PER_REV = 200;
const float MICROSTEPS  = 16.0f;
const float GEAR_RATIO  = 30.0f;

const uint32_t STEPS_PER_REV = MOTOR_FULL_STEPS_PER_REV * MICROSTEPS * GEAR_RATIO;
const float STEPS_PER_RAD = float(STEPS_PER_REV) / (2.0f * PI);
const float REV_PER_M = 1.0f / (2.0f * PI * WHEEL_RADIUS_M);
const float STEPS_PER_M = float(STEPS_PER_REV) * REV_PER_M;

const float DC_MAX_DUTY_FRACTION = 0.75f;
const int DC_MAX_DUTY = int(DC_MAX_DUTY_FRACTION * 255.0f);

// —————————————————————
// Timing & State
// —————————————————————
uint32_t stepPeriod[4] = {UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX};
const uint32_t stepPulseUs = 2;
uint32_t lastMicros[4] = {0, 0, 0, 0};
int mode = 0;
unsigned long lastSwitch = 0;

// —————————————————————
// Setup
// —————————————————————
void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);

  for (int i = 0; i < 4; i++) {
    pinMode(STEP_PINS[i], OUTPUT);
    pinMode(DIR_PINS[i], OUTPUT);
    pinMode(EN_PINS[i], OUTPUT);
    digitalWrite(STEP_PINS[i], HIGH);
    digitalWrite(EN_PINS[i], LOW);
  }

  for (int i = 0; i < 2; i++) {
    pinMode(DIR_D_PINS[i], OUTPUT);
    pinMode(EN_D_PINS[i], OUTPUT);
    digitalWrite(EN_D_PINS[i], LOW);
    ledcAttach(PWM_PINS[i], 20000, 8);
  }

  Serial.println("4-Steppers, 2-DC — geometry-aware mode cycling");
}

// —————————————————————
// Motor Controls
// —————————————————————
void setStepper(int idx, float mps, bool fwd) {
  float pps = fabs(mps * STEPS_PER_M);
  stepPeriod[idx] = (pps > 0) ? uint32_t(1e6f / pps) : UINT32_MAX;
  digitalWrite(DIR_PINS[idx], fwd ? LOW : HIGH);
}

void setDC(int idx, float mps, bool fwd) {
  int duty = constrain(int(fabs(mps) / 1.0f * DC_MAX_DUTY), 0, DC_MAX_DUTY);
  ledcWrite(PWM_PINS[idx], duty);
  digitalWrite(DIR_D_PINS[idx], fwd ? HIGH : LOW);
  digitalWrite(EN_D_PINS[idx], LOW);
}

void setSteerAngle(int idx, float angle_rad) {
  float speed = angle_rad * REV_PER_M;
  setStepper(idx, speed, angle_rad >= 0);
}

// —————————————————————
// Mode Dynamics
// —————————————————————
void driveHolonomic(float vx, float vy, float omega) {
  float steer = atan2(vy, vx);
  float v_trans = sqrt(vx * vx + vy * vy);
  float v_rot = fabs(omega) * (TRACK_WIDTH_M / 2.0f);
  float wheelSpeed = v_trans + v_rot;

  for (int i = 0; i < 4; i++) setSteerAngle(i, steer);
  for (int i = 0; i < 2; i++) setDC(i, wheelSpeed, wheelSpeed >= 0);
}
void driveSpin(float omega) {
  float steer = (omega >= 0) ? (PI / 2.0f) : (-PI / 2.0f);
  float wheelSpeed = fabs(omega) * (TRACK_WIDTH_M / 2.0f);
  for (int i = 0; i < 4; i++) setSteerAngle(i, steer);
  for (int i = 0; i < 2; i++) setDC(i, wheelSpeed, omega >= 0);
}

void driveAckermann(float vx, float steerAngle) {
  for (int i = 0; i < 4; i++) setSteerAngle(i, steerAngle);
  for (int i = 0; i < 2; i++) setDC(i, vx, vx >= 0);
}

// —————————————————————
// Main Loop
// —————————————————————
void loop() {
  uint32_t now = micros();
  for (int i = 0; i < 4; i++) {
    if (now - lastMicros[i] >= stepPeriod[i]) {
      lastMicros[i] = now;
      digitalWrite(STEP_PINS[i], LOW);
      delayMicroseconds(stepPulseUs);
      digitalWrite(STEP_PINS[i], HIGH);
    }
  }

  // Switch mode every 5s
  if (millis() - lastSwitch >= 5000) {
    mode = (mode + 1) % 3;
    Serial.printf("\n--- Mode %d ---\n", mode);
    switch (mode) {
      case 0: driveHolonomic(0.3, 0.1, 0.2); break;
      case 1: driveSpin(0.5); break;
      case 2: driveAckermann(0.2, 0.3); break;
    }
    lastSwitch = millis();
  }
}
