import cv2
import mediapipe as mp

#mp_hands = mp.solutions.hands
#mp_drawing = mp.solutions.drawing_utils
#hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.7)

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        print("Não foi possível acessar a câmera.")
        break
    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
   # results = hands.process(img_rgb)

    #if results.multi_hand_landmarks:
    #    for hand_landmarks in results.multi_hand_landmarks:
    #        mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
#
 #           ponto_4 = hand_landmarks[4] 
  #          h, w, c = frame.shape
   #         cx, cy = int(ponto_4.x * w), int(ponto_4.y * h)
    #        cv2.circle(frame, (cx, cy), 10, (255, 0, 255), cv2.FILLED)
    cv2.imshow('Detector de mãos', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break
cap.release()
cv2.destroyAllWindows()