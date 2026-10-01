import time
import math
import cv2
import mediapipe as mp
import numpy as np
from motor_UART import MotorUART
from pathlib import Path
from urllib.request import urlopen
from scservo_sdk import (
    PortHandler,
    sms_sts,
    COMM_SUCCESS,
)


# ============================================================
# Global parameters
# ============================================================

Camera_Index_Int = 2

int_abs_error_stop = 30
int_abs_error_start = 45

# Phone Arm Control Loop Coefficients
bool_Enable = True
float_KPP = 0.03
Max_Robarm_speed = 500

# Low Speed Control Loop Coefficients/Parameters
flt_KPower = 0.0003
flt_KSteering = 0.0002
flt_min_speed = 0.05
flt_max_speed = 0.15

BAUDRATE = 1_000_000

ADDR_TORQUE_ENABLE = 40
ADDR_GOAL_POSITION = 42
ADDR_GOAL_SPEED = 46

shoulder_size_px_target = 206
shoulder_target_px = (645,405)

bool_idle = True

# ============================================================
# MediaPipe Pose Landmarker model
# ============================================================

MODEL_PATH = Path("models/pose_landmarker_lite.task")

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "pose_landmarker/pose_landmarker_lite/float16/latest/"
    "pose_landmarker_lite.task"
)


# ============================================================
# Phone Arm global parameters
# ============================================================

Phone_ARM_COM = "COM9"

Phone_ARM_IDS = [1, 2, 3, 4, 6]

Phone_ARM_GOAL_POSITIONS = {
    1: 3058,
    2: 2064,
    3: 2040,
    4: 1955,
    6: 2070,
}

Phone_ARM_Min_POSITIONS = {
    1: 2607,
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
    1: 2984,
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

# ============================================================
# MediaPipe Model
# ============================================================

def get_model():

    MODEL_PATH.parent.mkdir(exist_ok=True)

    if not MODEL_PATH.exists():

        print("Downloading pose landmarker model...")

        with urlopen(MODEL_URL) as response:
            MODEL_PATH.write_bytes(response.read())

    return MODEL_PATH


# ============================================================
# Robot Arm Functions
# ============================================================

def enable_torque(arm, ARM_IDs):

    for arm_id in ARM_IDs:

        arm.write1ByteTxRx(
            arm_id,
            ADDR_TORQUE_ENABLE,
            1,
        )


def disable_torque(arm, ARM_IDs):

    for arm_id in ARM_IDs:

        arm.write1ByteTxRx(
            arm_id,
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

def initialize_position(arm, goal_positions):

    for arm_id, position in goal_positions.items():

        arm.write2ByteTxRx(
            arm_id,
            ADDR_GOAL_POSITION,
            position,
        )


def write_goal_position(arm, arm_id, goal_position):

    arm.write2ByteTxRx(
        arm_id,
        ADDR_GOAL_POSITION,
        goal_position,
    )


# ============================================================
# MediaPipe Pose Landmarker Setup
# ============================================================

BaseOptions = mp.tasks.BaseOptions

PoseLandmarker = mp.tasks.vision.PoseLandmarker

PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions

VisionRunningMode = mp.tasks.vision.RunningMode


options = PoseLandmarkerOptions(

    base_options=BaseOptions(
        model_asset_path=str(get_model())
    ),

    running_mode=VisionRunningMode.IMAGE,

    # Number of people we want MediaPipe to detect.
    # For the phone arm we only care about one person.
    num_poses=1,

    min_pose_detection_confidence=0.8,

    min_pose_presence_confidence=0.8,

    min_tracking_confidence=0.85,
)


detector = PoseLandmarker.create_from_options(options)


# ============================================================
# Initialize Phone Arm
# ============================================================

ARM_PortHandler = PortHandler(Phone_ARM_COM)

if not ARM_PortHandler.openPort():
    print("Could not open robot arm serial port")
    raise SystemExit(1)

if not ARM_PortHandler.setBaudRate(BAUDRATE):
    print("Could not set robot arm baud rate")
    raise SystemExit(1)


Phone_ARM = sms_sts(ARM_PortHandler)

enable_torque(
    Phone_ARM,
    Phone_ARM_IDS,
)

set_speed(
    Phone_ARM,
    Light_ARM_IDS,
    Max_Robarm_speed
)

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

set_speed(
    Light_ARM,
    Light_ARM_IDS,
    Max_Robarm_speed
)

initialize_position(Light_ARM, Light_ARM_GOAL_POSITIONS)

# ============================================================
# Initialize Camera
# ============================================================

camera = cv2.VideoCapture(Camera_Index_Int)

if not camera.isOpened():

    print("Could not open camera")
    raise SystemExit(1)


print("Camera opened. Press Q to quit.")

# ============================================================
# Initialize Motor UART
# ============================================================

motor_uart = MotorUART(
    port="COM5",
    baudrate=115200,
    timeout=0.1,
)

motor_uart.connect()
motor_uart.stop()

last_motor_send_time = time.perf_counter()
MOTOR_SEND_PERIOD_S = 0.02   # 50 Hz stop resend

# ============================================================
# Important MediaPipe Pose landmark indexes
#
# 0  = Nose
# 11 = Left Shoulder
# 12 = Right Shoulder
# 13 = Left Elbow
# 14 = Right Elbow
# 15 = Left Wrist
# 16 = Right Wrist
# 23 = Left Hip
# 24 = Right Hip
# ============================================================

NOSE = 0

LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12

LEFT_ELBOW = 13
RIGHT_ELBOW = 14

LEFT_WRIST = 15
RIGHT_WRIST = 16

LEFT_HIP = 23
RIGHT_HIP = 24


# ============================================================
# Main Loop
# ============================================================

try:

    roboarm_position = Phone_ARM_GOAL_POSITIONS[1]
    while True:

        success, frame = camera.read()

        if not success:

            print("Could not read frame")
            break


        frame_height, frame_width = frame.shape[:2]


        # ----------------------------------------------------
        # Convert OpenCV BGR image to RGB
        # ----------------------------------------------------

        rgb_frame = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB,
        )


        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb_frame,
        )


        # ----------------------------------------------------
        # Run MediaPipe Pose Landmarker
        # ----------------------------------------------------

        result = detector.detect(mp_image)


        # ----------------------------------------------------
        # Draw center of camera
        # ----------------------------------------------------

        frame_center_x = frame_width // 2
        frame_center_y = frame_height // 2


        cv2.drawMarker(
            frame,
            (frame_center_x, frame_center_y),
            (255, 0, 0),
            cv2.MARKER_CROSS,
            30,
            2,
        )


        # ----------------------------------------------------
        # Check whether a pose was detected
        # ----------------------------------------------------

        if result.pose_landmarks:

            # num_poses = 1, so use first detected person
            landmarks = result.pose_landmarks[0]


            # ------------------------------------------------
            # Get upper body landmarks
            # ------------------------------------------------

            left_shoulder = landmarks[LEFT_SHOULDER]

            right_shoulder = landmarks[RIGHT_SHOULDER]

            left_hip = landmarks[LEFT_HIP]

            right_hip = landmarks[RIGHT_HIP]

            nose = landmarks[NOSE]


            # ------------------------------------------------
            # Convert normalized coordinates (0.0 - 1.0)
            # into actual image pixels
            # ------------------------------------------------

            left_shoulder_x = int(
                left_shoulder.x * frame_width
            )

            left_shoulder_y = int(
                left_shoulder.y * frame_height
            )


            right_shoulder_x = int(
                right_shoulder.x * frame_width
            )

            right_shoulder_y = int(
                right_shoulder.y * frame_height
            )


            left_hip_x = int(
                left_hip.x * frame_width
            )

            left_hip_y = int(
                left_hip.y * frame_height
            )


            right_hip_x = int(
                right_hip.x * frame_width
            )

            right_hip_y = int(
                right_hip.y * frame_height
            )


            nose_x = int(
                nose.x * frame_width
            )

            nose_y = int(
                nose.y * frame_height
            )


            # ------------------------------------------------
            # Upper-body tracking target
            #
            # Midpoint between left and right shoulder
            # ------------------------------------------------

            target_x = (
                left_shoulder_x
                + right_shoulder_x
            ) // 2


            target_y = (
                left_shoulder_y
                + right_shoulder_y
            ) // 2

            shoulder_size_px = math.sqrt(
            (right_shoulder_x - left_shoulder_x)**2
            +
            (right_shoulder_y - left_shoulder_y)**2
            )

            if(bool_idle):
                now = time.perf_counter()
                if now - last_motor_send_time >= MOTOR_SEND_PERIOD_S:
                    motor_uart.stop()
                    last_motor_send_time = now
                if(bool_Enable and (abs(shoulder_target_px[0] - target_x) > int_abs_error_start)):
                    roboarm_position += int(float_KPP * (target_x - shoulder_target_px[0]))
                    phone_arm_position = max(Phone_ARM_Min_POSITIONS[1], min(Phone_ARM_Max_POSITIONS[1], roboarm_position))
                    light_arm_position = max(Light_ARM_Min_POSITIONS[1], min(Light_ARM_Max_POSITIONS[1], roboarm_position))
                    write_goal_position(Phone_ARM, 1, phone_arm_position)
                    write_goal_position(Light_ARM, 1, light_arm_position)
                if(abs(shoulder_size_px_target - shoulder_size_px) > int_abs_error_start):
                    bool_idle = False
            else:
                if(abs(shoulder_size_px_target - shoulder_size_px) < int_abs_error_stop):
                    bool_idle = True
                else:
                    left_power = flt_min_speed
                    right_power = flt_min_speed
                    left_power += flt_KPower * abs(shoulder_size_px_target - shoulder_size_px)
                    right_power += flt_KPower * abs(shoulder_size_px_target - shoulder_size_px)
                    left_power = min(flt_max_speed, max(flt_min_speed, left_power))
                    right_power = min(flt_max_speed, max(flt_min_speed, right_power))
                    steering_delta = flt_KSteering * abs(target_x - shoulder_target_px[0])
                    if(shoulder_size_px < shoulder_size_px_target):
                        now = time.perf_counter()
                        if now - last_motor_send_time >= MOTOR_SEND_PERIOD_S:
                            if(target_x < shoulder_target_px[0]):
                                left_power += steering_delta
                                left_power = min(flt_max_speed, max(flt_min_speed, left_power))
                            else:
                                right_power += steering_delta
                                right_power = min(flt_max_speed, max(flt_min_speed, right_power))
                            motor_uart.set_speed(-left_power, -right_power)
                            last_motor_send_time = now
                    else:
                        now = time.perf_counter()
                        if now - last_motor_send_time >= MOTOR_SEND_PERIOD_S:
                            if(target_x < shoulder_target_px[0]):
                                right_power += steering_delta
                                right_power = min(flt_max_speed, max(flt_min_speed, right_power))
                            else:
                                left_power += steering_delta
                                left_power = min(flt_max_speed, max(flt_min_speed, left_power))
                            motor_uart.set_speed(left_power, right_power)
                            last_motor_send_time = now
                    
            # ------------------------------------------------
            # Draw shoulders
            # ------------------------------------------------

            cv2.circle(
                frame,
                (left_shoulder_x, left_shoulder_y),
                8,
                (0, 255, 0),
                -1,
            )


            cv2.circle(
                frame,
                (right_shoulder_x, right_shoulder_y),
                8,
                (0, 255, 0),
                -1,
            )


            cv2.line(
                frame,
                (left_shoulder_x, left_shoulder_y),
                (right_shoulder_x, right_shoulder_y),
                (0, 255, 0),
                3,
            )


            # ------------------------------------------------
            # Draw torso
            # ------------------------------------------------

            cv2.line(
                frame,
                (left_shoulder_x, left_shoulder_y),
                (left_hip_x, left_hip_y),
                (0, 255, 0),
                2,
            )

            cv2.line(
                frame,
                (right_shoulder_x, right_shoulder_y),
                (right_hip_x, right_hip_y),
                (0, 255, 0),
                2,
            )

            cv2.line(
                frame,
                (left_hip_x, left_hip_y),
                (right_hip_x, right_hip_y),
                (0, 255, 0),
                2,
            )


            # ------------------------------------------------
            # Draw nose
            # ------------------------------------------------

            cv2.circle(
                frame,
                (nose_x, nose_y),
                5,
                (255, 255, 0),
                -1,
            )


            # ------------------------------------------------
            # Draw tracking target
            # ------------------------------------------------

            cv2.drawMarker(
                frame,
                (target_x, target_y),
                (0, 0, 255),
                cv2.MARKER_CROSS,
                30,
                3,
            )


            # Draw line showing tracking error
            cv2.line(
                frame,
                (frame_center_x, frame_center_y),
                (target_x, target_y),
                (0, 0, 255),
                2,
            )


            # ------------------------------------------------
            # Display tracking information
            # ------------------------------------------------

            cv2.putText(
                frame,
                f"Target: ({target_x}, {target_y})",
                (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )

            # ------------------------------------------------
            # Display calibration information
            # ------------------------------------------------

            debug_lines = [
                f"Frame Center: ({frame_center_x}, {frame_center_y})",
                f"Shoulder Target: ({target_x}, {target_y})",
                f"Shoulder Size: ({shoulder_size_px:.2f}) px",
            ]

            for i, text in enumerate(debug_lines):
                cv2.putText(
                    frame,
                    text,
                    (20, 30 + 30 * i),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )
        else:
            bool_idle = True
            now = time.perf_counter()

            if now - last_motor_send_time >= MOTOR_SEND_PERIOD_S:
                motor_uart.stop()
                last_motor_send_time = now

            cv2.putText(
                frame,
                "NO LANDMARK DETECTED - TRUCK STOP",
                (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )
            
        # ----------------------------------------------------
        # Display
        # ----------------------------------------------------

        cv2.imshow(
            "OpenCV + MediaPipe Pose Tracking",
            frame,
        )


        key = cv2.waitKey(1) & 0xFF

        if key == ord("q") or key == ord("Q"):
            break


finally:

    # --------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------

    if motor_uart is not None:
        motor_uart.stop()
        motor_uart.close()

    camera.release()

    detector.close()

    cv2.destroyAllWindows()

    ARM_PortHandler.closePort()
