#include <Arduino.h>

// —————————————————————
// Pin Definitions
// —————————————————————
// Stepper
const int STEP_PIN  = 16;
const int DIR_S_PIN = 17;
const int EN_S_PIN  = 4;   // active LOW
// DC Motor
const int PWM_D_PIN = 5;
const int DIR_D_PIN = 18;
const int EN_D_PIN  = 19;  // active HIGH

// —————————————————————
// Constants
// —————————————————————
const int PWM_FREQ = 20000;
const int PWM_RES  = 8;       // 8-bit resolution
const int DUTY_FIXED = 200;   // fixed duty for DC motor
const float PULSES_PER_M = 2000.0f;
const float TRACK_WIDTH_M = 0.5f;

// —————————————————————
// Stepper Timing
// —————————————————————
volatile float  stepPps     = 0;
uint32_t        stepPeriod  = UINT32_MAX;
const uint32_t  stepPulseUs = 2;
uint32_t        lastMicros  = 0;

// —————————————————————
// Init Functions
// —————————————————————
void setupStepper() {
  pinMode(STEP_PIN,   OUTPUT);
  pinMode(DIR_S_PIN,  OUTPUT);
  pinMode(EN_S_PIN,   OUTPUT);
  digitalWrite(EN_S_PIN, HIGH);  // disable
  digitalWrite(STEP_PIN, HIGH);
  delay(10);
  digitalWrite(EN_S_PIN, LOW);   // enable
}

void setupDC() {
  pinMode(DIR_D_PIN, OUTPUT);
  pinMode(EN_D_PIN,  OUTPUT);
  digitalWrite(EN_D_PIN, LOW);
  ledcAttach(PWM_D_PIN, PWM_FREQ, PWM_RES);
}

// —————————————————————
// Motor Control Functions
// —————————————————————
void updateStepperTiming() {
  stepPeriod = (stepPps > 0)
             ? uint32_t(1e6f / stepPps)
             : UINT32_MAX;
}

void setStepperFixed(float pps, bool fwd) {
  stepPps = pps;
  digitalWrite(DIR_S_PIN, fwd ? LOW : HIGH);
  updateStepperTiming();
  Serial.printf("Stepper PPS = %.1f, dir = %s\n", stepPps, fwd ? "FWD" : "REV");
}

void setDCFixed(int duty, bool fwd) {
  duty = constrain(duty, 0, 255);
  ledcWrite(PWM_D_PIN, duty);
  digitalWrite(DIR_D_PIN, fwd ? HIGH : LOW);
  digitalWrite(EN_D_PIN, duty > 0 ? HIGH : LOW);
  Serial.printf("DC duty = %d, dir = %s\n", duty, fwd ? "FWD" : "REV");
}

// —————————————————————
// Arduino Setup & Loop — Spin-in-Place with fixed duty
// —————————————————————
void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);

  setupStepper();
  setupDC();

  Serial.println("Spin-in-place test: Stepper and DC motor at fixed speed");

  setStepperFixed(1000.0, true);   // 1000 pulses per second
  setDCFixed(DUTY_FIXED, true);    // fixed 200 duty
}

void loop() {
  uint32_t now = micros();
  if (now - lastMicros >= stepPeriod) {
    lastMicros = now;
    digitalWrite(STEP_PIN, LOW);
    delayMicroseconds(stepPulseUs);
    digitalWrite(STEP_PIN, HIGH);
  }
}