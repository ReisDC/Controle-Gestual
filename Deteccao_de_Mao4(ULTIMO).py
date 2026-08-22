# Este código faz as mesmas funcionalidades das versões anteriores mas com a adição de detectar a distancia das mãos.
#
#
##
#           Ainda a ser codado
###
###
import cv2
import mediapipe as mp
import time
import os
from collections import deque
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Guarda as ultimas 5 posições dos pontos das mãos para suavizar o jitter
historico_pontos = {i: deque(maxlen=5) for i in range(21)}
# Uma lista comum é boa para adicionar valores no final mas muito ruim para remover o primerio valor,
# o deque resolve esse problema pois ele adiciona e remove em ambos os lados.
def calcular_media(ponto_index, nova_posicao):
    historico_pontos[ponto_index].append(nova_posicao)
    media_x = int(sum(p[0] for p in historico_pontos[ponto_index]) / len(historico_pontos[ponto_index]))
    media_y = int(sum(p[1] for p in historico_pontos[ponto_index]) / len(historico_pontos[ponto_index]))
    return (media_x, media_y)

dir_path = os.path.dirname(os.path.realpath(__file__))
model_path = os.path.join(dir_path, 'hand_landmarker.task')

base_options = python.BaseOptions(model_asset_path=model_path)
options = vision.HandLandmarkerOptions(
    base_options=base_options,
    num_hands=4, #Limita o numero de mãos detectadas.
    running_mode=vision.RunningMode.VIDEO,
    # Aumentar esses valores ajuda a reduzir falsos positivos e instabilidade
    min_hand_detection_confidence=0.5, #Detecta a presença de uma mão na camera.  
    min_hand_presence_confidence=0.5, #Detecta a presença da mão a cada frame.
    min_tracking_confidence=0.5) #Detecta as juntas do dedos das mãos.

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
            h, w, _ = frame.shape

            pontos = []
            for lm in landmarks:
                cx, cy = int(lm.x * w), int(lm.y * h)
                pontos.append((cx, cy)) 

                cv2.drawMarker(frame, (cx, cy), (0, 0, 0), markerType=cv2.MARKER_CROSS, markerSize=10, thickness=2) # Desenha um marcador de cruz

            conexoes = [
                (0, 1), (1, 2), (2, 3), (3, 4),      # Polegar
                (0, 5), (5, 6), (6, 7), (7, 8),      # Indicador
                (9, 10), (10, 11), (11, 12),         # Médio
                (13, 14), (14, 15), (15, 16),        # Anelar
                (0, 17), (17, 18), (18, 19), (19, 20),# Mindinho
                (5, 9), (9, 13), (13, 17)            # Palma
            ]

            for con in conexoes:
                p1 = pontos[con[0]]
                p2 = pontos[con[1]]
                cv2.line(frame, p1, p2, (255, 255, 255 ), 2) # Desenha as conexões entre os pontos

    cv2.imshow('Detecção de mãos', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()