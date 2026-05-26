const int PWM_PIN = 5;    // PWM to SV via low-pass filter
const int DIR_PIN = 18;   // Direction → F/R (HIGH = FWD)
const int EN_PIN  = 19;   // Enable → EN (LOW = Run)

const int PWM_FREQ = 20000;
const int PWM_RES  = 8;       // 8-bit = 0–255
const int DUTY = 255;         // ~78% duty, tune for your motor

void setup() {
  Serial.begin(115200);
  while (!Serial) delay(10);

  pinMode(DIR_PIN, OUTPUT);
  pinMode(EN_PIN,  OUTPUT);
  digitalWrite(EN_PIN, LOW);  // Enable motor

  ledcAttach(PWM_PIN, PWM_FREQ, PWM_RES);
  Serial.println("BLDC constant speed test started.");
}

void loop() {
  // Forward
  digitalWrite(DIR_PIN, HIGH);
  ledcWrite(PWM_PIN, DUTY);
  Serial.println("Forward @ duty 200");
  delay(5);

}
