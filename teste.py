import mediapipe as mp
import os

print(f"Caminho do MediaPipe: {mp.__file__}")
print(f"Conteúdo do módulo: {dir(mp)}")

try:
    from mediapipe.python.solutions import hands as mp_hands
    print("Sucesso ao importar via caminho direto!")
except ImportError as e:
    print(f"Falha na importação direta: {e}")