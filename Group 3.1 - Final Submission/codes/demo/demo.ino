#include <Arduino.h>
#include <math.h>

// —————————————————————
// Pin Definitions (1 Stepper + 1 DC Motor)
// —————————————————————
const int STEP_PIN = 16;
const int DIR_STEP_PIN = 17;
const int EN_STEP_PIN = 4;
const int PWM_PIN = 5;
const int DIR_DC_PIN = 18;
const int EN_DC_PIN = 19;

// —————————————————————
// Geometry & Constants
// —————————————————————
const float TRACK_WIDTH_M = 0.40f;
const float WHEEL_BASE_M = 0.70f;
const float WHEEL_RADIUS_M = 0.10f;

const uint32_t MOTOR_FULL_STEPS_PER_REV = 200;
const float MICROSTEPS = 16.0f;
const float GEAR_RATIO = 30.0f;

const uint32_t STEPS_PER_REV = MOTOR_FULL_STEPS_PER_REV * MICROSTEPS * GEAR_RATIO;
const float STEPS_PER_RAD = float(STEPS_PER_REV) / (2.0f * PI);
const float REV_PER_M = 1.0f / (2.0f * PI * WHEEL_RADIUS_M);
const float STEPS_PER_M = float(STEPS_PER_REV) * REV_PER_M;

const float DC_MAX_DUTY_FRACTION = 0.75f;
const int DC_MAX_DUTY = int(DC_MAX_DUTY_FRACTION * 255.0f);

// —————————————————————
// Timing & State
// —————————————————————
uint32_t stepPeriod = UINT32_MAX;
const uint32_t stepPulseUs = 2;
uint32_t lastMicros = 0;
unsigned long modeStart = 0;
int state = 0;
int mode = 0;

// —————————————————————
// Setup
// —————————————————————
void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);

  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_STEP_PIN, OUTPUT);
  pinMode(EN_STEP_PIN, OUTPUT);
  digitalWrite(STEP_PIN, HIGH);
  digitalWrite(EN_STEP_PIN, LOW);

  pinMode(DIR_DC_PIN, OUTPUT);
  pinMode(EN_DC_PIN, OUTPUT);
  digitalWrite(EN_DC_PIN, LOW);
  ledcAttach(PWM_PIN, 20000, 8);

  Serial.println("1 Stepper + 1 DC | Dynamic Mode Sequence with Pause");
}

// —————————————————————
// Motor Control
// —————————————————————
void setStepper(float mps, bool fwd) {
  float pps = fabs(mps * STEPS_PER_M);
  stepPeriod = (pps > 0) ? uint32_t(1e6f / pps) : UINT32_MAX;
  digitalWrite(DIR_STEP_PIN, fwd ? LOW : HIGH);
}

void setDC(float mps, bool fwd) {
  int duty = constrain(int(fabs(mps) / 1.0f * DC_MAX_DUTY), 0, DC_MAX_DUTY);
  ledcWrite(PWM_PIN, duty);
  digitalWrite(DIR_DC_PIN, fwd ? HIGH : LOW);
  digitalWrite(EN_DC_PIN, LOW);
}

void setSteerAngle(float angle_rad) {
  float speed = angle_rad * REV_PER_M;
  setStepper(speed, angle_rad >= 0);
}

// —————————————————————
// Modes
// —————————————————————
void loop() {
  uint32_t now = micros();
  if (now - lastMicros >= stepPeriod) {
    lastMicros = now;
    digitalWrite(STEP_PIN, LOW);
    delayMicroseconds(stepPulseUs);
    digitalWrite(STEP_PIN, HIGH);
  }

  unsigned long t = millis() - modeStart;

  if (state == -1) {
    setDC(0, true);
    setStepper(0, true);
    if (t > 2000) {
      state = 0;
      mode = (mode + 1) % 3;
      modeStart = millis();
    }
    return;
  }

  switch (mode) {
    case 0: // Holonomic arc + straight
    Serial.println("Holonomic arc + straight");
      if (state == 0) {
        setSteerAngle(PI / 6);
        setDC(0.2, true);
        if (t > 5000) { state = 1; modeStart = millis(); }
      } else if (state == 1) {
        setSteerAngle(0);
        setDC(0.2, true);
        if (t > 2000) { state = -1; modeStart = millis(); }
      }
      break;

    case 1: // Spin in place
      if (t == 0) Serial.println("Spin-in-place");
      setSteerAngle(PI / 2);
      setDC(0.2, true);
      if (t > 3000) { state = -1; modeStart = millis(); }
      break;

    case 2: // Ackermann
      Serial.println("Ackermann");
      if (state == 0) {
        setSteerAngle(0);
        setDC(0.2, true);
        if (t > 2000) { state = 1; modeStart = millis(); }
      } else if (state == 1) {
        setSteerAngle(PI / 4);
        setDC(0.2, true);
        if (t > 2000) { state = 2; modeStart = millis(); }
      } else if (state == 2) {
        setSteerAngle(0);
        setDC(0.2, true);
        if (t > 1000) { state = -1; modeStart = millis(); }
      }
      break;
  }
}
