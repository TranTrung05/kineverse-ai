/*
 * KINEVERSE – Sensor Glove firmware mẫu (ESP32 + 5 flex sensor + MPU6050)
 * Xuất 1 dòng JSON mỗi 20 ms (50 Hz) qua Serial 115200:
 *   {"t":12345,"f":[thumb,index,middle,ring,pinky],"imu":[ax,ay,az,gx,gy,gz]}
 *   f   : ADC thô 0..4095 (ADC1)         imu : gia tốc (g), vận tốc góc (dps)
 *
 * Đấu nối (mỗi flex sensor là một cầu phân áp):
 *   3V3 --- flex --- GPIO --- R 10k --- GND
 *   Flex: thumb=GPIO32, index=GPIO33, middle=GPIO34, ring=GPIO35, pinky=GPIO36
 *   MPU6050: SDA=GPIO21, SCL=GPIO22, VCC=3V3, GND=GND, AD0=GND (địa chỉ 0x68)
 * Không dùng thư viện ngoài (chỉ Wire). Chưa kiểm thử trên phần cứng thật – cần hiệu chỉnh khi lắp ráp.
 */
#include <Wire.h>

const int FLEX_PINS[5] = {32, 33, 34, 35, 36};
const uint8_t MPU_ADDR = 0x68;
const unsigned long PERIOD_MS = 20;
const int OVERSAMPLE = 4;

float gyroBias[3] = {0, 0, 0};
bool imuOk = false;
unsigned long lastTick = 0;

bool readMpu(float *out) {            // out: ax ay az gx gy gz
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)MPU_ADDR, 14) != 14) return false;
  int16_t v[7];
  for (int i = 0; i < 7; i++) { int16_t hi = Wire.read(); v[i] = (hi << 8) | Wire.read(); }
  out[0] = v[0] / 16384.0f; out[1] = v[1] / 16384.0f; out[2] = v[2] / 16384.0f;   // ±2g
  out[3] = v[4] / 131.0f;   out[4] = v[5] / 131.0f;   out[5] = v[6] / 131.0f;     // ±250 dps (bỏ v[3] = nhiệt độ)
  return true;
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  Wire.begin(21, 22);
  Wire.setClock(400000);
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B); Wire.write(0x00);   // đánh thức MPU6050
  imuOk = (Wire.endTransmission() == 0);
  if (imuOk) {                           // bù độ lệch gyro: giữ găng đứng yên ~1 giây khi cấp nguồn
    float acc[3] = {0, 0, 0}, s[6]; int n = 0;
    for (int i = 0; i < 100; i++) { if (readMpu(s)) { for (int k = 0; k < 3; k++) acc[k] += s[3 + k]; n++; } delay(10); }
    if (n) for (int k = 0; k < 3; k++) gyroBias[k] = acc[k] / n;
  }
}

void loop() {
  unsigned long now = millis();
  if (now - lastTick < PERIOD_MS) return;
  lastTick = now;

  int f[5];
  for (int i = 0; i < 5; i++) {
    long sum = 0;
    for (int k = 0; k < OVERSAMPLE; k++) sum += analogRead(FLEX_PINS[i]);
    f[i] = sum / OVERSAMPLE;
  }
  float m[6] = {0, 0, 0, 0, 0, 0};
  if (imuOk && readMpu(m)) { m[3] -= gyroBias[0]; m[4] -= gyroBias[1]; m[5] -= gyroBias[2]; }

  char buf[200];
  snprintf(buf, sizeof(buf),
           "{\"t\":%lu,\"f\":[%d,%d,%d,%d,%d],\"imu\":[%.2f,%.2f,%.2f,%.1f,%.1f,%.1f]}",
           now, f[0], f[1], f[2], f[3], f[4], m[0], m[1], m[2], m[3], m[4], m[5]);
  Serial.println(buf);
}
