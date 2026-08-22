# Este codigo detecta apenas os pontos das mãos, sem desenhar as conexões entre eles.

import cv2
import mediapipe as mp
import os
import time
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

dir_path = os.path.dirname(os.path.realpath(__file__))
model_path = os.path.join(dir_path, 'hand_landmarker.task')

base_options = python.BaseOptions(model_asset_path=model_path)
options = vision.HandLandmarkerOptions(
    base_options=base_options,
    num_hands=2,
    running_mode=vision.RunningMode.VIDEO,
    # Aumentar esses valores ajuda a reduzir falsos positivos e instabilidade
    min_hand_detection_confidence=0.7, 
    min_hand_presence_confidence=0.7,
    min_tracking_confidence=0.7)

detector = vision.HandLandmarker.create_from_options(options)

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    frame = cv2.flip(frame, 1)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
    timestamp = int(time.time() * 1000) # Timestamp em milissegundos
    detection_result = detector.detect_for_video(mp_image, timestamp) # Detecta as mãos

    # Desenha os pontos se encontrar algo
    if detection_result.hand_landmarks:
        for landmarks in detection_result.hand_landmarks:
            for landmark in landmarks:
                # Desenha círculos simples em cada ponto detectado
                h, w, _ = frame.shape
                x, y = int(landmark.x * w), int(landmark.y * h)
                #cv2.putText(frame, str(id), (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1) # Desenha o ID do ponto. Serve para debugar
                cv2.drawMarker(frame, (x, y), (0, 0, 0), markerType=cv2.MARKER_CROSS, markerSize=10, thickness=2) # Desenha um marcador de cruz
                # o (0, 0, 0) muda a cor do marcador
                #cv2.circle(frame, (x, y), 5, (0, 255, 0), -1) # Desenha um círculo preenchido

    cv2.imshow('Detecção de mãos', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()