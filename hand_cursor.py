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

# Quando True (somente Windows), a janela de preview ignora cliques do mouse:
# o clique "atravessa" a janela e vai para o que estiver atras dela. Isso evita
# que um clique na barra de titulo/bordas da janela inicie o loop modal do
# Windows (arrastar/redimensionar), que congela o processamento.
# Para sair: tecla "q" na janela, Ctrl+Shift+Q (global) ou Ctrl+C no terminal.
JANELA_ATRAVESSAVEL = False

CAMINHO_MODELO = Path(__file__).with_name("models") / "hand_landmarker.task"
TITULO_JANELA = "Hand Cursor - Preview"


@dataclass(frozen=True)
class Configuracoes:
    indice_camera: int = 0
    suavizacao: float = 0.80
    limiar_jitter: float = 7.0
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

    # --- SEGURANCA DO BOTAO DO MOUSE ---
    # Se a mao de gestos sumir com o botao pressionado, solta apos este tempo.
    tempo_perda_mao_soltar: float = 0.05

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


def tornar_janela_atravessavel(titulo: str) -> bool:
    """Faz a janela ignorar cliques do mouse (Windows). Retorna True se conseguiu."""
    if platform.system() != "Windows":
        return False

    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, titulo)
    if not hwnd:
        return False

    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    LWA_ALPHA = 0x00000002

    estilo = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, estilo | WS_EX_LAYERED | WS_EX_TRANSPARENT)
    # Janela em camadas precisa de atributos definidos; 255 = totalmente opaca.
    user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
    return True


def atalho_global_de_saida() -> bool:
    """Ctrl+Shift+Q em qualquer lugar do sistema (Windows)."""
    if platform.system() != "Windows":
        return False

    import ctypes

    get_state = ctypes.windll.user32.GetAsyncKeyState
    VK_CONTROL, VK_SHIFT, VK_Q = 0x11, 0x10, 0x51
    return bool(get_state(VK_CONTROL) & 0x8000 and get_state(VK_SHIFT) & 0x8000 and get_state(VK_Q) & 0x8000)


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
    """Captura, detecta gestos e controla o mouse.

    IMPORTANTE: esta thread NAO chama nenhuma funcao de janela do OpenCV
    (imshow, waitKey, namedWindow...). A janela e gerenciada pela thread
    principal. Assim, mesmo que a janela congele (ex.: usuario clica na barra
    de titulo), o rastreamento continua rodando e o botao do mouse nunca fica
    preso.
    """

    def __init__(self, config, dependencias):
        super().__init__(daemon=True)
        self.config = config
        self.cv2, self.np, self.mp, self.BaseOptions, self.HandLandmarker, self.HandLandmarkerOptions, self.HandLandmarksConnections, self.RunningMode, self.pyautogui = dependencias
        self.executando = True
        self._trava_previa = threading.Lock()
        self._previa = None

    def obter_previa(self):
        with self._trava_previa:
            return self._previa

    def _publicar_previa(self, previa) -> None:
        with self._trava_previa:
            self._previa = previa

    def run(self):
        pyautogui = self.pyautogui
        cv2 = self.cv2
        np = self.np
        mp = self.mp
        config = self.config

        #medidas de desempenho
        tempo_ultimo_frame = time.monotonic()
        fps_contador = 0
        fps_atual = 30.0
        tempo_acumulado_fps = 0.0
        lista_fps = []
        lista_latencias = []

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

        ultimo_visto_mao_gestos = time.monotonic()

        try:
            while self.executando:
                inicio_ciclo = time.monotonic()

                # Cálculo contínuo de FPS
                delta_frame = inicio_ciclo - tempo_ultimo_frame
                tempo_ultimo_frame = inicio_ciclo
                if delta_frame > 0:
                    fps_instantaneo = 1.0 / delta_frame
                    fps_atual = (fps_atual * 0.8) + (fps_instantaneo * 0.2)

                camera_ok, quadro = camera.read()
                if not camera_ok:
                    break

                quadro = cv2.flip(quadro, 1)
                rgb = cv2.cvtColor(quadro, cv2.COLOR_BGR2RGB)
                rgb = np.ascontiguousarray(rgb)
                imagem = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                tempo_ms = int(time.monotonic() * 1000)

                inicio_inferencia = time.monotonic()
                resultado = detector_mao.detect_for_video(imagem, tempo_ms)
                fim_inferencia = time.monotonic()

                # Latência em milissegundos (ciclo + inferência)
                latencia_frame_ms = (fim_inferencia - inicio_ciclo) * 1000

                lista_fps.append(fps_atual)
                lista_latencias.append(latencia_frame_ms)

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

                    distancia_movimento = math.hypot(alvo_x - mouse_x, alvo_y - mouse_y)

                    # Se a alteração for menor que o limiar de jitter, consideramos apenas ruído e travamos a posição
                    if distancia_movimento > config.limiar_jitter:
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
                # 3.1 SEGURANCA: nunca deixar o botao do mouse preso
                # Se a mao de gestos sumiu (ou o zoom assumiu) com o botao
                # pressionado, solta depois de um curto tempo.
                # -------------------------------------------------------------
                if mao_gestos is not None and not gesto_zoom_ativo:
                    ultimo_visto_mao_gestos = time.monotonic()
                elif (
                    mouse_esta_pressionado
                    and time.monotonic() - ultimo_visto_mao_gestos > config.tempo_perda_mao_soltar
                ):
                    pyautogui.mouseUp(button="left")
                    mouse_esta_pressionado = False
                    pinca_de_clique_esquerdo_estava_ativa = False
                    inicio_pinca_selecao = None

                # -------------------------------------------------------------
                # 4. DESENHO DA PREVIA (apenas desenha; quem exibe e a thread principal)
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
                    cv2.putText(quadro, f"FPS: {fps_atual:.1f} | Latencia: {latencia_frame_ms:.1f}ms", 
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    self._publicar_previa(redimensionar_previa(cv2, quadro, config.largura_previa))

        finally:
            if mouse_esta_pressionado:
                pyautogui.mouseUp(button="left")
            detector_mao.close()
            camera.release()
            self.executando = False

            # Relatório final de FPS e latência
            if lista_fps and lista_latencias:
                media_fps = sum(lista_fps) / len(lista_fps)
                media_latencia = sum(lista_latencias) / len(lista_latencias)
                print("\n" + "="*40)
                print("RELATÓRIO FINAL DE DESEMPENHO:")
                print(f" FPS Médio Geral: {media_fps:.2f}")
                print(f" Latência Média Geral: {media_latencia:.2f} ms")
                print("="*40 + "\n")

    def parar(self):
        self.executando = False


def executar_janela_previa(cv2, rastreador: ThreadRastreamento, config: Configuracoes) -> None:
    """Loop da janela de preview. Roda na THREAD PRINCIPAL (exigencia do OpenCV/Windows)."""
    cv2.namedWindow(TITULO_JANELA, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(TITULO_JANELA, config.largura_previa, 720)
    try:
        cv2.setWindowProperty(TITULO_JANELA, cv2.WND_PROP_TOPMOST, 1)
    except cv2.error:
        pass

    janela_configurada = False

    while rastreador.is_alive() and rastreador.executando:
        previa = rastreador.obter_previa()

        if previa is not None:
            cv2.imshow(TITULO_JANELA, previa)

            if not janela_configurada:
                if JANELA_ATRAVESSAVEL and not tornar_janela_atravessavel(TITULO_JANELA):
                    print("Aviso: nao foi possivel tornar a janela atravessavel por cliques.")
                janela_configurada = True

        tecla = cv2.waitKey(10) & 0xFF
        if tecla == ord("q") or atalho_global_de_saida():
            break

        if janela_configurada:
            try:
                if cv2.getWindowProperty(TITULO_JANELA, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break


def principal() -> None:
    dependencias = carregar_dependencias()
    cv2 = dependencias[0]
    config = Configuracoes()

    thread_camera = ThreadRastreamento(config, dependencias)
    thread_camera.start()

    try:
        if SHOW_CAMERA:
            executar_janela_previa(cv2, thread_camera, config)
        else:
            while thread_camera.is_alive():
                thread_camera.join(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        thread_camera.parar()
        thread_camera.join(timeout=3)
        if SHOW_CAMERA:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    principal()