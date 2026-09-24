from __future__ import annotations

import math
import os
import platform
import threading
import time
from dataclasses import dataclass
from pathlib import Path

PASTA_MATPLOTLIB = Path(__file__).with_name(".matplotlib")
PASTA_MATPLOTLIB.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(PASTA_MATPLOTLIB))
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("GLOG_minloglevel", "3")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

SHOW_CAMERA = True

CAMINHO_MODELO = Path(__file__).with_name("models") / "hand_landmarker.task"
TITULO_JANELA = "Hand Cursor - Preview"


@dataclass(frozen=True)
class Configuracoes:
    indice_camera: int = 0
    suavizacao: float = 0.20
    distancia_clique: float = 0.075
    distancia_soltar: float = 0.105
    tempo_ativacao_selecao: float = 0.25
    confianca_deteccao: float = 0.7
    confianca_rastreamento: float = 0.7
    largura_camera: int = 640
    altura_camera: int = 480
    fps_camera: int = 30
    largura_previa: int = 960
    controle_esquerda: float = 0.20
    controle_direita: float = 0.80
    controle_topo: float = 0.20
    controle_base: float = 0.80
    limite_dedos_juntos_scroll: float = 0.08
    
    # --- SCROLL CONTINUO ---
    zona_morta_scroll: float = 0.03
    velocidade_maxima_scroll: int = 150

    # --- ZOOM CONTINUO ---
    zona_morta_zoom: float = 0.02
    intervalo_zoom_segundos: float = 0.08


def interpolar(atual: float, alvo: float, quantidade: float) -> float:
    return atual + (alvo - atual) * quantidade


def limitar(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def mapear_intervalo(
    valor: float,
    origem_minima: float,
    origem_maxima: float,
    destino_minimo: float,
    destino_maximo: float,
) -> float:
    valor = limitar(valor, origem_minima, origem_maxima)
    tamanho_origem = origem_maxima - origem_minima
    tamanho_destino = destino_maximo - destino_minimo
    return destino_minimo + ((valor - origem_minima) / tamanho_origem) * tamanho_destino


def mapear_mao_para_tela(ponta_indicador, largura_tela: int, altura_tela: int, config: Configuracoes):
    x = mapear_intervalo(
        ponta_indicador.x,
        config.controle_esquerda,
        config.controle_direita,
        0,
        largura_tela - 1,
    )
    y = mapear_intervalo(
        ponta_indicador.y,
        config.controle_topo,
        config.controle_base,
        0,
        altura_tela - 1,
    )
    return x, y


def obter_limites_da_tela(pyautogui):
    if platform.system() == "Windows":
        import ctypes

        user32 = ctypes.windll.user32
        esquerda = user32.GetSystemMetrics(76)
        topo = user32.GetSystemMetrics(77)
        largura = user32.GetSystemMetrics(78)
        altura = user32.GetSystemMetrics(79)
        return esquerda, topo, largura, altura

    largura, altura = pyautogui.size()
    return 0, 0, largura, altura


def distancia_entre_pontos(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def indicador_esta_esticado(pontos_mao) -> bool:
    ponta_indicador = pontos_mao[8]
    base_indicador = pontos_mao[5]
    pulso = pontos_mao[0]
    return distancia_entre_pontos(ponta_indicador, pulso) > distancia_entre_pontos(base_indicador, pulso) * 1.25


def esta_em_pinca(ponta_dedo, ponta_polegar, config: Configuracoes, mouse_pressionado: bool) -> bool:
    distancia = distancia_entre_pontos(ponta_dedo, ponta_polegar)
    limite = config.distancia_soltar if mouse_pressionado else config.distancia_clique
    return distancia < limite


def mao_esta_fechada(pontos_mao) -> bool:
    pulso = pontos_mao[0]
    pares_dedos = ((8, 6), (12, 10), (16, 14), (20, 18))
    dedos_fechados = 0

    for indice_ponta, indice_junta in pares_dedos:
        ponta = pontos_mao[indice_ponta]
        junta = pontos_mao[indice_junta]
        ponta_abaixo_da_junta = ponta.y > junta.y
        ponta_perto_da_palma = distancia_entre_pontos(ponta, pulso) < distancia_entre_pontos(junta, pulso) * 1.15

        if ponta_abaixo_da_junta or ponta_perto_da_palma:
            dedos_fechados += 1

    return dedos_fechados >= 4


def dedos_indicador_e_medio_levantados_juntos(pontos_mao, config: Configuracoes) -> bool:
    ponta_indicador = pontos_mao[8]
    junta_indicador = pontos_mao[6]
    base_indicador = pontos_mao[5]

    ponta_medio = pontos_mao[12]
    junta_medio = pontos_mao[10]
    base_medio = pontos_mao[9]

    ponta_anelar = pontos_mao[16]
    base_anelar = pontos_mao[13]

    ponta_minimo = pontos_mao[20]
    base_minimo = pontos_mao[17]

    pulso = pontos_mao[0]

    indicador_reto = (
        distancia_entre_pontos(ponta_indicador, pulso) > distancia_entre_pontos(junta_indicador, pulso) * 1.15
        and distancia_entre_pontos(ponta_indicador, pulso) > distancia_entre_pontos(base_indicador, pulso) * 1.3
    )

    medio_reto = (
        distancia_entre_pontos(ponta_medio, pulso) > distancia_entre_pontos(junta_medio, pulso) * 1.15
        and distancia_entre_pontos(ponta_medio, pulso) > distancia_entre_pontos(base_medio, pulso) * 1.3
    )

    anelar_fechado = distancia_entre_pontos(ponta_anelar, pulso) < distancia_entre_pontos(base_anelar, pulso) * 1.2
    minimo_fechado = distancia_entre_pontos(ponta_minimo, pulso) < distancia_entre_pontos(base_minimo, pulso) * 1.2

    dedos_juntos = distancia_entre_pontos(ponta_indicador, ponta_medio) < config.limite_dedos_juntos_scroll

    return indicador_reto and medio_reto and anelar_fechado and minimo_fechado and dedos_juntos


def gesto_zoom_indicador_e_polegar_esticados(pontos_mao) -> bool:
    pulso = pontos_mao[0]
    
    ponta_polegar = pontos_mao[4]
    base_polegar = pontos_mao[2]
    
    ponta_indicador = pontos_mao[8]
    base_indicador = pontos_mao[5]
    
    ponta_medio = pontos_mao[12]
    base_medio = pontos_mao[9]
    
    ponta_anelar = pontos_mao[16]
    base_anelar = pontos_mao[13]
    
    ponta_minimo = pontos_mao[20]
    base_minimo = pontos_mao[17]

    indicador_reto = distancia_entre_pontos(ponta_indicador, pulso) > distancia_entre_pontos(base_indicador, pulso) * 1.3
    polegar_reto = distancia_entre_pontos(ponta_polegar, pulso) > distancia_entre_pontos(base_polegar, pulso) * 1.2

    medio_dobrado = distancia_entre_pontos(ponta_medio, pulso) < distancia_entre_pontos(base_medio, pulso) * 1.2
    anelar_dobrado = distancia_entre_pontos(ponta_anelar, pulso) < distancia_entre_pontos(base_anelar, pulso) * 1.2
    minimo_dobrado = distancia_entre_pontos(ponta_minimo, pulso) < distancia_entre_pontos(base_minimo, pulso) * 1.2

    separados = distancia_entre_pontos(ponta_indicador, ponta_polegar) > 0.08

    return indicador_reto and polegar_reto and medio_dobrado and anelar_dobrado and minimo_dobrado and separados


def executar_zoom(pyautogui, direcao: str):
    """Executa o atalho de zoom de forma compatível com diferentes teclados (ABNT2 e US)."""
    if direcao == "in":
        # Dispara Zoom In
        pyautogui.hotkey('ctrl', '+')
        pyautogui.hotkey('ctrl', 'add')
    elif direcao == "out":
        # Dispara Zoom Out com variações para garantir funcionamento no ABNT2/Windows
        pyautogui.hotkey('ctrl', '-')
        pyautogui.hotkey('ctrl', 'subtract')


def carregar_dependencias():
    print("Carregando OpenCV...", flush=True)
    import cv2
    import numpy as np

    print("Carregando MediaPipe...", flush=True)
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        HandLandmarker,
        HandLandmarkerOptions,
        HandLandmarksConnections,
        RunningMode,
    )

    print("Carregando controle do mouse...", flush=True)
    import pyautogui

    return (
        cv2,
        np,
        mp,
        BaseOptions,
        HandLandmarker,
        HandLandmarkerOptions,
        HandLandmarksConnections,
        RunningMode,
        pyautogui,
    )


def desenhar_area_de_controle(cv2, quadro, config: Configuracoes) -> None:
    altura, largura, _ = quadro.shape
    canto_superior_esquerdo = (
        int(config.controle_esquerda * largura),
        int(config.controle_topo * altura),
    )
    canto_inferior_direito = (
        int(config.controle_direita * largura),
        int(config.controle_base * altura),
    )
    cv2.rectangle(quadro, canto_superior_esquerdo, canto_inferior_direito, (255, 255, 255), 1)


def redimensionar_previa(cv2, quadro, largura_previa: int):
    altura, largura, _ = quadro.shape
    altura_previa = int(altura * (largura_previa / largura))
    return cv2.resize(quadro, (largura_previa, altura_previa))


def criar_detector_de_mao(
    BaseOptions,
    HandLandmarker,
    HandLandmarkerOptions,
    RunningMode,
    config: Configuracoes,
):
    if not CAMINHO_MODELO.exists():
        raise FileNotFoundError(
            "Modelo da mao nao encontrado. Rode: "
            ".\\.venv\\Scripts\\python.exe download_model.py"
        )

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(CAMINHO_MODELO)),
        running_mode=RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=config.confianca_deteccao,
        min_hand_presence_confidence=config.confianca_deteccao,
        min_tracking_confidence=config.confianca_rastreamento,
    )
    return HandLandmarker.create_from_options(options)


def desenhar_mao(cv2, quadro, pontos_mao, conexoes, cor_linha=(35, 190, 95)) -> None:
    altura, largura, _ = quadro.shape

    for conexao in conexoes:
        inicio = pontos_mao[conexao.start]
        fim = pontos_mao[conexao.end]
        ponto_inicio = (int(inicio.x * largura), int(inicio.y * altura))
        ponto_fim = (int(fim.x * largura), int(fim.y * altura))
        cv2.line(quadro, ponto_inicio, ponto_fim, cor_linha, 2)

    for ponto_mao in pontos_mao:
        ponto = (int(ponto_mao.x * largura), int(ponto_mao.y * altura))
        cv2.circle(quadro, ponto, 4, (255, 255, 255), -1)


class ThreadRastreamento(threading.Thread):
    def __init__(self, config, dependencias):
        super().__init__()
        self.config = config
        self.cv2, self.np, self.mp, self.BaseOptions, self.HandLandmarker, self.HandLandmarkerOptions, self.HandLandmarksConnections, self.RunningMode, self.pyautogui = dependencias
        self.executando = True

    def run(self):
        pyautogui = self.pyautogui
        cv2 = self.cv2
        np = self.np
        mp = self.mp
        config = self.config

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0
        pyautogui.MINIMUM_DURATION = 0
        pyautogui.MINIMUM_SLEEP = 0
        tela_esquerda, tela_topo, largura_tela, altura_tela = obter_limites_da_tela(pyautogui)

        camera = None
        for idx in range(config.indice_camera, 5):
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    camera = cap
                    print(f"Câmera iniciada com sucesso no índice {idx}.")
                    break
                cap.release()

        if camera is None:
            print("Erro: Nenhuma câmera funcional foi encontrada.")
            self.executando = False
            return

        camera.set(cv2.CAP_PROP_FRAME_WIDTH, config.largura_camera)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, config.altura_camera)
        camera.set(cv2.CAP_PROP_FPS, config.fps_camera)
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if SHOW_CAMERA:
            cv2.namedWindow(TITULO_JANELA, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(TITULO_JANELA, config.largura_previa, 720)
            try:
                cv2.setWindowProperty(TITULO_JANELA, cv2.WND_PROP_TOPMOST, 1)
            except cv2.error:
                pass

        detector_mao = criar_detector_de_mao(
            self.BaseOptions,
            self.HandLandmarker,
            self.HandLandmarkerOptions,
            self.RunningMode,
            config,
        )

        mouse_x, mouse_y = pyautogui.position()
        pinca_de_clique_direito_estava_ativa = False
        pinca_de_clique_esquerdo_estava_ativa = False
        mouse_esta_pressionado = False
        inicio_pinca_selecao: float | None = None
        
        ponto_neutro_scroll_y: float | None = None
        mao_cursor_estava_visivel = False

        distancia_neutra_zoom: float | None = None
        ultimo_comando_zoom: float = 0

        try:
            while self.executando:
                camera_ok, quadro = camera.read()
                if not camera_ok:
                    break

                quadro = cv2.flip(quadro, 1)
                rgb = cv2.cvtColor(quadro, cv2.COLOR_BGR2RGB)
                rgb = np.ascontiguousarray(rgb)
                imagem = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                tempo_ms = int(time.monotonic() * 1000)
                resultado = detector_mao.detect_for_video(imagem, tempo_ms)

                mao_cursor = None
                mao_gestos = None

                if resultado.hand_landmarks and resultado.handedness:
                    for hand_landmarks, handedness_category in zip(resultado.hand_landmarks, resultado.handedness):
                        if handedness_category:
                            lado = handedness_category[0].category_name
                            if lado == "Left":
                                mao_cursor = hand_landmarks
                            elif lado == "Right":
                                mao_gestos = hand_landmarks

                # -------------------------------------------------------------
                # 1. VERIFICAÇÃO DO GESTO DE ZOOM (AMBAS AS MÃOS)
                # -------------------------------------------------------------
                gesto_zoom_ativo = False

                if mao_cursor is not None and mao_gestos is not None:
                    if gesto_zoom_indicador_e_polegar_esticados(mao_cursor) and gesto_zoom_indicador_e_polegar_esticados(mao_gestos):
                        gesto_zoom_ativo = True
                        
                        distancia_atual_maos = distancia_entre_pontos(mao_cursor[5], mao_gestos[5])

                        if distancia_neutra_zoom is None:
                            distancia_neutra_zoom = distancia_atual_maos

                        diferenca = distancia_atual_maos - distancia_neutra_zoom
                        agora = time.monotonic()

                        if abs(diferenca) > config.zona_morta_zoom:
                            if agora - ultimo_comando_zoom >= config.intervalo_zoom_segundos:
                                if diferenca > 0:
                                    executar_zoom(pyautogui, "in")
                                    texto_zoom = "ZOOM IN (+)"
                                else:
                                    executar_zoom(pyautogui, "out")
                                    texto_zoom = "ZOOM OUT (-)"

                                ultimo_comando_zoom = agora

                                if SHOW_CAMERA:
                                    cv2.putText(quadro, texto_zoom, (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 255), 3)
                        else:
                            if SHOW_CAMERA:
                                cv2.putText(quadro, "ZOOM: NEUTRO", (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)

                if not gesto_zoom_ativo:
                    distancia_neutra_zoom = None

                # -------------------------------------------------------------
                # 2. MOVIMENTO DO CURSOR
                # -------------------------------------------------------------
                if not gesto_zoom_ativo and mao_cursor is not None and indicador_esta_esticado(mao_cursor):
                    ponta_indicador_cursor = mao_cursor[8]
                    alvo_x, alvo_y = mapear_mao_para_tela(
                        ponta_indicador_cursor,
                        largura_tela,
                        altura_tela,
                        config,
                    )
                    alvo_x += tela_esquerda
                    alvo_y += tela_topo

                    if not mao_cursor_estava_visivel:
                        mouse_x, mouse_y = pyautogui.position()
                        mao_cursor_estava_visivel = True

                    mouse_x = interpolar(mouse_x, alvo_x, config.suavizacao)
                    mouse_y = interpolar(mouse_y, alvo_y, config.suavizacao)
                    pyautogui.moveTo(mouse_x, mouse_y, duration=0)
                else:
                    mao_cursor_estava_visivel = False

                # -------------------------------------------------------------
                # 3. GESTOS DE CLIQUE E SCROLL
                # -------------------------------------------------------------
                gesto_scroll_ativo = False

                if not gesto_zoom_ativo and mao_gestos is not None:
                    ponta_indicador = mao_gestos[8]
                    ponta_medio = mao_gestos[12]
                    ponta_polegar = mao_gestos[4]

                    pinca_de_clique_esquerdo_ativa = esta_em_pinca(
                        ponta_indicador,
                        ponta_polegar,
                        config,
                        pinca_de_clique_esquerdo_estava_ativa,
                    )
                    pinca_selecao_ativa = esta_em_pinca(
                        ponta_medio,
                        ponta_polegar,
                        config,
                        mouse_esta_pressionado,
                    )

                    gesto_clique_direito = mao_esta_fechada(mao_gestos) and not pinca_selecao_ativa
                    gesto_scroll_ativo = dedos_indicador_e_medio_levantados_juntos(mao_gestos, config)

                    if gesto_scroll_ativo:
                        if mao_cursor is not None:
                            y_atual_cursor = mao_cursor[8].y

                            if ponto_neutro_scroll_y is None:
                                ponto_neutro_scroll_y = y_atual_cursor

                            deslocamento = y_atual_cursor - ponto_neutro_scroll_y

                            if abs(deslocamento) > config.zona_morta_scroll:
                                direcao = -1 if deslocamento > 0 else 1
                                fator_distancia = (abs(deslocamento) - config.zona_morta_scroll) / 0.15
                                fator_distancia = limitar(fator_distancia, 0.0, 1.0)

                                quantidade_scroll = int(direcao * fator_distancia * config.velocidade_maxima_scroll)
                                if quantidade_scroll != 0:
                                    pyautogui.scroll(quantidade_scroll)

                                if SHOW_CAMERA:
                                    texto = "ROLANDO PARA CIMA" if direcao > 0 else "ROLANDO PARA BAIXO"
                                    cv2.putText(quadro, texto, (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
                            else:
                                if SHOW_CAMERA:
                                    cv2.putText(quadro, "SCROLL: NEUTRO", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)

                    elif gesto_clique_direito:
                        if mouse_esta_pressionado:
                            pyautogui.mouseUp(button="left")
                            mouse_esta_pressionado = False

                        pinca_de_clique_direito_estava_ativa = True
                        pinca_de_clique_esquerdo_estava_ativa = False
                        inicio_pinca_selecao = None
                    elif pinca_de_clique_direito_estava_ativa and not gesto_clique_direito:
                        pyautogui.click(button="right")
                        pinca_de_clique_direito_estava_ativa = False
                    else:
                        if pinca_selecao_ativa:
                            pinca_de_clique_esquerdo_estava_ativa = False
                            if inicio_pinca_selecao is None:
                                inicio_pinca_selecao = time.monotonic()
                            elif (
                                not mouse_esta_pressionado
                                and time.monotonic() - inicio_pinca_selecao >= config.tempo_ativacao_selecao
                            ):
                                pyautogui.mouseDown(button="left")
                                mouse_esta_pressionado = True
                        elif mouse_esta_pressionado:
                            inicio_pinca_selecao = None
                            pyautogui.mouseUp(button="left")
                            mouse_esta_pressionado = False
                            pinca_de_clique_esquerdo_estava_ativa = False
                        elif pinca_de_clique_esquerdo_ativa:
                            inicio_pinca_selecao = None
                            pinca_de_clique_esquerdo_estava_ativa = True
                        elif pinca_de_clique_esquerdo_estava_ativa:
                            pyautogui.click(button="left")
                            pinca_de_clique_esquerdo_estava_ativa = False
                        else:
                            inicio_pinca_selecao = None

                if not gesto_scroll_ativo or mao_cursor is None:
                    ponto_neutro_scroll_y = None

                # -------------------------------------------------------------
                # 4. DESENHO E TRATAMENTO DE EVENTOS DA JANELA OPENCV
                # -------------------------------------------------------------
                if SHOW_CAMERA:
                    if mao_cursor is not None:
                        desenhar_mao(
                            cv2,
                            quadro,
                            mao_cursor,
                            self.HandLandmarksConnections.HAND_CONNECTIONS,
                            cor_linha=(255, 0, 255) if gesto_zoom_ativo else (255, 150, 0),
                        )

                    if mao_gestos is not None:
                        desenhar_mao(
                            cv2,
                            quadro,
                            mao_gestos,
                            self.HandLandmarksConnections.HAND_CONNECTIONS,
                            cor_linha=(255, 0, 255) if gesto_zoom_ativo else (0, 165, 255),
                        )

                    desenhar_area_de_controle(cv2, quadro, config)
                    previa = redimensionar_previa(cv2, quadro, config.largura_previa)
                    
                    cv2.imshow(TITULO_JANELA, previa)
                    
                    # Processa 1ms de eventos sem bloquear a thread
                    tecla = cv2.waitKey(1) & 0xFF
                    if tecla == ord("q"):
                        self.executando = False

                    try:
                        if cv2.getWindowProperty(TITULO_JANELA, cv2.WND_PROP_VISIBLE) < 1:
                            self.executando = False
                    except cv2.error:
                        pass

        finally:
            if mouse_esta_pressionado:
                pyautogui.mouseUp()
            detector_mao.close()
            camera.release()
            if SHOW_CAMERA:
                cv2.destroyAllWindows()

    def parar(self):
        self.executando = False


def principal() -> None:
    dependencias = carregar_dependencias()
    config = Configuracoes()

    thread_camera = ThreadRastreamento(config, dependencias)
    thread_camera.start()
    thread_camera.join()


if __name__ == "__main__":
    principal()