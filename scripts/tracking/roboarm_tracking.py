import time
import cv2
import mediapipe as mp
import numpy as np
from pathlib import Path
from urllib.request import urlopen
from scservo_sdk import (
    PortHandler,
    sms_sts,
    COMM_SUCCESS,
)


#Global parameters
Camer_Index_Int = 2

int_abs_error = 10

BAUDRATE = 1_000_000

ADDR_TORQUE_ENABLE = 40
ADDR_GOAL_POSITION = 42
ADDR_GOAL_SPEED = 46

# Phone Arm global Parameters
Phone_ARM_COM = "COM9"
Phone_ARM_IDS = [1, 2, 3, 4, 6]
Phone_ARM_GOAL_POSITIONS = {
    1: 2034,
    2: 2064,
    3: 2040,
    4: 1955,
    6: 2096,
}

Phone_ARM_Min_POSITIONS = {
    1: 758,
    2: 815,
    3: 883,
    4: 863,
    6: 2096,
}

Phone_ARM_Max_POSITIONS = {
    1: 3483,
    2: 3176,
    3: 3089,
    4: 1955,
    6: 2096,
}

# ============================================================
# Light Arm global parameters
# ============================================================

Light_ARM_COM = "COM8"

Light_ARM_IDS = [1, 2, 3, 4, 5]

Light_ARM_GOAL_POSITIONS = {
    1: 1880,
    2: 2900,
    3: 2472,
    4: 1669,
    5: 2629,
}

Light_ARM_Min_POSITIONS = {
    1: 619,
    2: 1684,
    3: 1308,
    4: 547,
    5: 1398,
}

Light_ARM_Max_POSITIONS = {
    1: 3313,
    2: 4085,
    3: 3511,
    4: 2879,
    5: 4090,
}

# Phone Arm Control Loop Coefficients
float_KPP = 0.1

MODEL_PATH = Path("models/blaze_face_short_range.tflite")
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"


def get_model():
    MODEL_PATH.parent.mkdir(exist_ok=True)

    if not MODEL_PATH.exists():
        print("Downloading face detector model...")
        with urlopen(MODEL_URL) as response:
            MODEL_PATH.write_bytes(response.read())

    return MODEL_PATH

def enable_torque(arm, ARM_IDs):
    for id in ARM_IDs:
        arm.write1ByteTxRx(
            id,
            ADDR_TORQUE_ENABLE,
            1,
        )

def disable_torque(arm, ARM_IDs):
    for id in ARM_IDs:
            arm.write1ByteTxRx(
                id,
                ADDR_TORQUE_ENABLE,
                0,
            )
            
def set_speed(arm, ARM_IDs, speed):

    for arm_id in ARM_IDs:

        arm.write2ByteTxRx(
            arm_id,
            ADDR_GOAL_SPEED,
            speed,
        )

def initialize_position(arm,goal_positions):
    for id,position in  goal_positions.items():
        arm.write2ByteTxRx(
            id,
            ADDR_GOAL_POSITION,
            position,
        )

def write_goal_position(arm, arm_id, goal_position):
    arm.write2ByteTxRx(
            arm_id,
            ADDR_GOAL_POSITION,
            goal_position,
        )

BaseOptions = mp.tasks.BaseOptions
FaceDetector = mp.tasks.vision.FaceDetector
FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions
VisionRunningMode = mp.tasks.vision.RunningMode

options = FaceDetectorOptions(
    base_options=BaseOptions(model_asset_path=str(get_model())),
    running_mode=VisionRunningMode.IMAGE,
    min_detection_confidence=0.8,
)

detector = FaceDetector.create_from_options(options)

#initalizing Phone Arm 
ARM_PortHandler = PortHandler(Phone_ARM_COM)
ARM_PortHandler.openPort()
ARM_PortHandler.setBaudRate(BAUDRATE)
Phone_ARM = sms_sts(ARM_PortHandler)
enable_torque(Phone_ARM, Phone_ARM_IDS)
initialize_position(Phone_ARM, Phone_ARM_GOAL_POSITIONS)

# ============================================================
# Initialize Light Arm
# ============================================================

Light_ARM_PortHandler = PortHandler(Light_ARM_COM)

if not Light_ARM_PortHandler.openPort():
    print("Could not open robot arm serial port")
    raise SystemExit(1)

if not Light_ARM_PortHandler.setBaudRate(BAUDRATE):
    print("Could not set robot arm baud rate")
    raise SystemExit(1)


Light_ARM = sms_sts(Light_ARM_PortHandler)

enable_torque(
    Light_ARM,
    Light_ARM_IDS,
)

initialize_position(Light_ARM, Light_ARM_GOAL_POSITIONS)

camera = cv2.VideoCapture(Camer_Index_Int)

if not camera.isOpened():
    print("Could not open camera")
    raise SystemExit(1)

target_x = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH)) // 2
x_servo_position = Phone_ARM_GOAL_POSITIONS[1]

print("Camera opened. Press Q to quit.")
while True:
    success, frame = camera.read()

    if not success:
        print("Could not read frame")
        break

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

    result = detector.detect(mp_image)

    for detection in result.detections:
        box = detection.bounding_box

        x = box.origin_x
        y = box.origin_y
        w = box.width
        h = box.height

        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        
        error = (x + w // 2) - target_x
        
        if(abs(error) > int_abs_error):
            x_servo_position += int(float_KPP * error)
            x_servo_position = max(Phone_ARM_Min_POSITIONS[1], min(Phone_ARM_Max_POSITIONS[1], x_servo_position))
            x_light_sevro_position = max(Light_ARM_Min_POSITIONS[1], min(Light_ARM_Max_POSITIONS[1], x_servo_position))
            write_goal_position(Phone_ARM, 1, x_servo_position)
            write_goal_position(Light_ARM, 1, x_light_sevro_position)
    
        score = detection.categories[0].score
        cv2.putText(
            frame,
            f"Face {score:.2f}",
            (x, max(20, y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )
    cv2.imshow("OpenCV + MediaPipe Face Detection", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord("q") or key == ord("Q"):
        break

camera.release()
detector.close()
cv2.destroyAllWindows()