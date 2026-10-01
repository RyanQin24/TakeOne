#include <Arduino.h>
#include <VescUart.h>
#include <WiFi.h>
#include <esp_now.h>

// Drivetrain data structure
typedef struct Drivetrain {
  int LeftPower;
  int RightPower;
} Drivetrain;

// ESP32 UART pins
#define VESC_RX 16
#define VESC_TX 17

// ESP32 GPIO pins
#define Button_GPIO 12
#define LED_GPIO 2

// RightESC CAN ID
#define CAN_ID_Right 2

// Safety Caps
#define UART_FWD_Cap 0.15
#define UART_REV_Cap -0.15
#define REM_FWD_Cap 0.15
#define REM_REV_Cap -0.15
#define MotorTimeOut 60
#define ParseTimeout 10
#define LeftDeadZoneLow 480
#define LeftDeadZoneHigh 525
#define RightDeadZoneLow 494
#define RightDeadZoneHigh 535

//ESP32 Parameters
#define DeBounce_Timeout 200
#define RX_Buffer 14

// global variables
VescUart VESC;
Drivetrain drivetrain;
volatile bool AutoFlag;
volatile bool updateRFspeed = false;
volatile unsigned long lastTime = 0;
volatile unsigned long lastMotorTime = 0;
volatile float leftDutyCycle = 0.0;
volatile float rightDutyCycle = 0.0;
volatile int leftRFSignal = -1;
volatile int rightRFSignal = -1;

// Callback function that will be executed when data is received
void OnDataRecv(const esp_now_recv_info *info, const uint8_t *incomingData, int len) {
  memcpy(&drivetrain, incomingData, sizeof(drivetrain));
  leftRFSignal = drivetrain.LeftPower;
  rightRFSignal = drivetrain.RightPower;
  updateRFspeed = true;
  lastTime = millis();
}

//button ISR
void IRAM_ATTR buttonISR()
{
    if(millis() - lastTime > DeBounce_Timeout){
        AutoFlag = !AutoFlag;
        digitalWrite(LED_GPIO, AutoFlag);
        lastTime = millis();
        leftDutyCycle = 0.0;
        rightDutyCycle = 0.0;
        leftRFSignal = -1;
        rightRFSignal = -1;
        while(Serial.available()){
            Serial.read();
        }
    }
}

void SetRFSpeed(){
    //left motor
    if(leftRFSignal == -1){
        leftDutyCycle = 0.0;
    }else if(leftRFSignal < LeftDeadZoneLow){
        leftDutyCycle = LinearMap(leftRFSignal,LeftDeadZoneLow ,0, 0.0, REM_REV_Cap);
    }else if(leftRFSignal > LeftDeadZoneHigh){
        leftDutyCycle = LinearMap(leftRFSignal,LeftDeadZoneHigh ,1023, 0.0, REM_FWD_Cap);
    }else{
        leftDutyCycle = 0.0;
    }
    //right motor
    if(rightRFSignal == -1){
        rightDutyCycle = 0.0;
    }else if(rightRFSignal < RightDeadZoneLow){
        rightDutyCycle = LinearMap(rightRFSignal,RightDeadZoneLow ,0, 0.0, REM_REV_Cap);
    }else if(rightRFSignal > RightDeadZoneHigh){
        rightDutyCycle = LinearMap(rightRFSignal,RightDeadZoneHigh ,1023, 0.0, REM_FWD_Cap);
    }else{
        rightDutyCycle = 0.0;
    }
}

float LinearMap(int input, int minval, int maxval, float minoutval, float maxoutval){
    return (minoutval + (input - minval) * (maxoutval - minoutval) / (maxval - minval));
}

//format in leftDC,RightDC\n
void ParseUART(){
    if(Serial.available()>0){
        String left_duty = "";
        String right_duty = "";
        short state = 0;
        unsigned long lastParseTime = millis();
        while(millis() - lastParseTime < ParseTimeout){
            if(Serial.available()>0){
                char c = Serial.read();
                if(c == '\n'){
                    leftDutyCycle = left_duty.toFloat();
                    rightDutyCycle = right_duty.toFloat();
                    if(leftDutyCycle > UART_FWD_Cap){
                        leftDutyCycle = UART_FWD_Cap;
                    }else if (leftDutyCycle < UART_REV_Cap){
                        leftDutyCycle = UART_REV_Cap;
                    }
                    if(rightDutyCycle > UART_FWD_Cap){
                        rightDutyCycle = UART_FWD_Cap;
                    }else if (rightDutyCycle < UART_REV_Cap){
                        rightDutyCycle = UART_REV_Cap;
                    }                      
                    lastMotorTime = millis();
                    return;
                }
                else if(c == ','){
                    state = 1;
                }else if( state == 1){
                    right_duty += c;
                }else{
                    left_duty += c;
                }
            }
        }
        leftRFSignal = -1;
        rightRFSignal = -1;
        leftDutyCycle = 0.0;
        rightDutyCycle = 0.0;
    }
}

void setup()
{
    //ESP aux IO initiate
    Serial.begin(115200);
    pinMode(Button_GPIO, INPUT_PULLUP);
    pinMode(LED_GPIO, OUTPUT);
    AutoFlag = false;
    digitalWrite(LED_GPIO, AutoFlag);
    attachInterrupt(digitalPinToInterrupt(Button_GPIO), buttonISR, FALLING);
    Serial.setRxBufferSize(RX_Buffer);
    delay(8000);

    // Initializing ESC
    Serial2.begin(115200, SERIAL_8N1, VESC_RX, VESC_TX);
    VESC.setSerialPort(&Serial2);

    Serial.println("VESC UART initialized");

    delay(1000);

    // Set device as a Wi-Fi Station
    WiFi.mode(WIFI_STA);

    // Init ESP-NOW
    if (esp_now_init() != 0) {
        Serial.println("Error initializing ESP-NOW");
        return;
    }
  
    // Setting up the Wifi Module so it listend to remote's command
    // get recv packet info
    esp_now_register_recv_cb(OnDataRecv);

    lastMotorTime = millis();
}

void loop()
{
    if(AutoFlag){
        ParseUART();
    }else{
        if(updateRFspeed){
            SetRFSpeed();
            updateRFspeed = false;
            lastMotorTime = millis();
        }
    }
    //time out for UART in case ESP-Now Hangs
    if(millis() - lastMotorTime > MotorTimeOut){
        leftRFSignal = -1;
        rightRFSignal = -1;
        leftDutyCycle = 0.0;
        rightDutyCycle = 0.0;
        Serial.println("Timed Out Bozo");
    }
    VESC.setDuty(leftDutyCycle);
    VESC.setDuty(rightDutyCycle, CAN_ID_Right);
}