"""
Chronométrage de la chaîne d'analyse, étape par étape.

Répond à l'objectif « Mesurable » du mémoire : donner une latence chiffrée, et
non une estimation. Le principe est le même que celui du banc d'évaluation :
aucune réimplémentation. Les fonctions réellement exécutées en séance sont
enveloppées à chaud dans un compteur, le code de production n'est pas modifié,
et les chiffres portent donc sur le système tel qu'il tourne.

DEUX RÉGIMES À NE PAS CONFONDRE
-------------------------------
La boucle d'analyse (api/main.py) acquiert les deux canaux EN PARALLÈLE : le
visage est échantillonné pendant que le micro enregistre. Le coût de la chaîne
faciale est donc AMORTI dans la durée de la fenêtre, tant qu'une image se
traite en moins de FACE_SAMPLE_INTERVAL. Il ne s'ajoute pas au délai ressenti.

Ce qui s'y ajoute, c'est uniquement ce qui suit la fermeture de la fenêtre :
agrégation du visage, inférence vocale, fusion, écriture BLE. C'est ce total
que le rapport appelle « chemin critique ».

    python -m tools.latency --video ../../Video/generated_video.mp4 --windows 20
    python -m tools.latency --video ... --ble        # ajoute l'écriture GATT
"""
import argparse
import csv
import json
import os
import platform
import statistics
import sys
import time
from collections import OrderedDict
from typing import Dict, List

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (  # noqa: E402
    ANALYSIS_WINDOW_SECONDS,
    CAPTURE_MAX_SIZE,
    EMOTIEFFLIB_MODEL,
    EMOTIEFFLIB_VA_GAIN,
    FACE_SAMPLE_INTERVAL,
    SAMPLERATE,
    SEUIL_DISSONANCE_DISTANCE,
    VOICE_SUBWINDOWS,
)
from services.analysis_session import AnalysisSession  # noqa: E402
from services.emotion_service import emotion_service  # noqa: E402
from tools.evaluate_corpus import load_audio  # noqa: E402


# --- Collecte des durées ---------------------------------------------------

class Chrono:
    """Accumule des durées en millisecondes, par étape nommée."""

    def __init__(self):
        self.series: "OrderedDict[str, List[float]]" = OrderedDict()

    def add(self, stage: str, ms: float) -> None:
        self.series.setdefault(stage, []).append(ms)

    def wrap(self, owner, attr: str, stage: str):
        """
        Enveloppe une méthode déjà en place par un compteur.

        Aucune modification du code de production : on remplace l'attribut sur
        l'instance vivante, l'appel réel est conservé tel quel.
        """
        original = getattr(owner, attr)

        def timed(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                self.add(stage, (time.perf_counter() - t0) * 1000.0)

        try:
            setattr(owner, attr, timed)
        except (AttributeError, TypeError) as exc:
            # Certains objets natifs (liaisons C++ de MediaPipe) refusent qu'on
            # leur pose un attribut. L'etape est alors simplement absente du
            # rapport, ce qui vaut mieux qu'un chiffre invente.
            print("  Etape '%s' non instrumentable (%s)" % (stage, exc))
        return original

    def drop_warmup(self, n: int) -> None:
        """
        Retire les n premières mesures de chaque étape.

        La première inférence d'un modèle ONNX alloue ses tampons et charge ses
        noyaux : elle coûte plusieurs fois le régime établi. La compter
        reviendrait à décrire un démarrage, pas un fonctionnement.
        """
        for stage, values in self.series.items():
            if len(values) > n:
                self.series[stage] = values[n:]


def stats(values: List[float]) -> Dict[str, float]:
    v = sorted(values)
    n = len(v)
    return {
        "n": n,
        "min": v[0],
        "mediane": statistics.median(v),
        "p95": v[min(n - 1, int(round(0.95 * (n - 1))))],
        "max": v[-1],
        "moyenne": statistics.fmean(v),
        "ecart_type": statistics.pstdev(v) if n > 1 else 0.0,
    }


# --- Matériel --------------------------------------------------------------

def _memoire_totale_go() -> str:
    """Mémoire physique installée, sans dépendance externe."""
    try:
        import ctypes

        class _MemStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = _MemStatus()
        status.dwLength = ctypes.sizeof(_MemStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return "%.0f" % (status.ullTotalPhys / (1024 ** 3))
    except Exception:
        return "inconnue"


def _memoire_processus_mo() -> float:
    """Empreinte mémoire résidente du processus d'analyse, en mégaoctets."""
    try:
        import ctypes
        from ctypes import wintypes

        class _Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong),
                        ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        # Les types doivent être déclarés : sans cela ctypes traite le
        # pseudo-handle du processus comme un entier 32 bits, l'appel échoue
        # silencieusement et renvoie zéro.
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        recuperer = ctypes.windll.psapi.GetProcessMemoryInfo
        recuperer.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), ctypes.c_ulong]
        recuperer.restype = wintypes.BOOL

        counters = _Counters()
        counters.cb = ctypes.sizeof(_Counters)
        if not recuperer(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return 0.0
        return counters.WorkingSetSize / 1e6
    except Exception:
        return 0.0


def hardware() -> Dict[str, str]:
    """Configuration matérielle, sans quoi les chiffres ne sont pas reproductibles."""
    info = {
        "systeme": "%s %s" % (platform.system(), platform.release()),
        "version": platform.version(),
        "machine": platform.machine(),
        "processeur": platform.processor() or "inconnu",
        "python": platform.python_version(),
        "coeurs_logiques": str(os.cpu_count()),
    }
    info["memoire_totale_go"] = _memoire_totale_go()

    if platform.system() == "Windows":
        # platform.processor() ne renvoie qu'une famille sur Windows. Le nom
        # commercial exact vient du registre, sans dépendance supplémentaire.
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            info["processeur"] = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
            winreg.CloseKey(key)
        except Exception:
            pass
    return info


def runtime_backend() -> str:
    """Backend d'exécution effectif du modèle facial, et fournisseurs ONNX actifs."""
    try:
        import onnxruntime
        providers = onnxruntime.get_available_providers()
        return "onnxruntime %s | fournisseurs : %s" % (
            onnxruntime.__version__, ", ".join(providers),
        )
    except Exception:
        return "onnxruntime non importable"


# --- Mesures ---------------------------------------------------------------

def measure_capture(chrono: Chrono, region, n: int) -> None:
    """
    Capture d'écran réelle, par le même objet que la boucle d'analyse.

    On mesure la zone telle que le HUD la définit, réduction à CAPTURE_MAX_SIZE
    comprise : c'est bien le coût payé à chaque image en séance.
    """
    from utils.screen_capture import ScreenCapture

    cap = ScreenCapture()
    cap.set_hud_coords(*region)
    ok = 0
    for _ in range(n):
        t0 = time.perf_counter()
        frame = cap.capture_hud_array()
        dt = (time.perf_counter() - t0) * 1000.0
        if frame is not None:
            chrono.add("capture_hud", dt)
            ok += 1
    if ok == 0:
        print("  ATTENTION : aucune capture d'ecran n'a abouti (session verrouillee,")
        print("  bureau distant ou permissions). L'etape capture sera absente.")


def load_frames(video: str, n: int) -> List[np.ndarray]:
    """
    Images de test, préparées exactement comme la capture réelle les fournit.

    Un visage réel est nécessaire : sur une image sans visage, MediaPipe sort
    immédiatement et l'étape EmotiEffLib n'est jamais atteinte, ce qui donnerait
    une latence flatteuse et fausse.
    """
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(1, int(round(fps * FACE_SAMPLE_INTERVAL)))
    frames, idx = [], 0
    while len(frames) < n:
        ok, frame = cap.read()
        if not ok:
            if not frames:
                break
            # Clip plus court que le nombre d'images demandé : on reboucle.
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            idx = 0
            continue
        if idx % stride == 0:
            h, w = frame.shape[:2]
            longest = max(h, w)
            if longest > CAPTURE_MAX_SIZE:
                s = CAPTURE_MAX_SIZE / float(longest)
                frame = cv2.resize(frame, (max(1, int(w * s)), max(1, int(h * s))),
                                   interpolation=cv2.INTER_AREA)
            frames.append(frame)
        idx += 1
    cap.release()
    return frames


def measure_ble(chrono: Chrono, n: int) -> None:
    """
    Écriture GATT réelle vers la montre.

    Ne mesure QUE l'écriture, pas la durée du motif de vibration : le
    raccrochage différé appartient à ce qui est ressenti au poignet, pas au
    chemin critique de l'alerte.

    Portée exacte de la mesure, à déclarer : l'écriture est faite sans accusé
    de réception (write_gatt_char avec response=False). Le chiffre relevé est
    donc le temps de remise du paquet à la pile Bluetooth du système, et non un
    aller-retour jusqu'à la montre. La transmission physique y ajoute au plus
    un intervalle de connexion BLE. C'est une borne inférieure, pas un total.
    """
    import asyncio
    from services.ble_service import BLEService, ble_service

    async def run():
        await ble_service.connect(sync_time=False)
        if not ble_service.is_connected:
            print("  Montre non connectee : etape BLE ignoree.")
            return
        for i in range(n):
            await ble_service.vibrate()
            if BLEService.last_write_latency_ms is not None:
                chrono.add("ble_write", float(BLEService.last_write_latency_ms))
            # Espacement volontaire : deux vibrations collées ne mesureraient
            # plus l'ecriture mais la file d'attente de la montre.
            await asyncio.sleep(3.0)
        await ble_service.disconnect()

    try:
        asyncio.run(run())
    except Exception as exc:
        print("  Mesure BLE impossible : %s" % exc)


# --- Restitution -----------------------------------------------------------

LIBELLES = OrderedDict([
    ("capture_hud", "Capture de la zone HUD (par image)"),
    ("mediapipe_detect", "Detection du visage, MediaPipe (par image)"),
    ("emotiefflib_predict", "Estimation faciale, EmotiEffLib (par image)"),
    ("analyze_face_frame", "  -> chaine faciale complete (par image)"),
    ("aggregate_face_window", "Agregation du visage sur la fenetre"),
    ("detect_audio_emotion", "Inference vocale, wav2vec 2.0 (fenetre de %.1f s)"
                             % ANALYSIS_WINDOW_SECONDS),
    ("detect_dissonance", "Fusion et logique floue"),
    ("process_window", "  -> decision complete (post-fenetre)"),
    ("ble_write", "Ecriture GATT vers la montre"),
])

AMORTIES = ("capture_hud", "mediapipe_detect", "emotiefflib_predict", "analyze_face_frame")


def report(chrono: Chrono, args) -> Dict[str, Dict[str, float]]:
    resultats = OrderedDict()
    for stage in LIBELLES:
        if chrono.series.get(stage):
            resultats[stage] = stats(chrono.series[stage])

    hw = hardware()
    print()
    print("=" * 84)
    print("CONFIGURATION")
    print("=" * 84)
    print("  Machine        : %s, %s coeurs logiques, %s Go de memoire"
          % (hw["processeur"], hw["coeurs_logiques"], hw["memoire_totale_go"]))
    print("  Systeme        : %s (%s)" % (hw["systeme"], hw["machine"]))
    print("  Python         : %s" % hw["python"])
    print("  Execution      : %s" % runtime_backend())
    print("  Modele facial  : %s | gain valence/arousal %.2f"
          % (EMOTIEFFLIB_MODEL, EMOTIEFFLIB_VA_GAIN))
    print("  Fenetre        : %.1f s | image toutes les %.2f s | capture reduite a %d px"
          % (ANALYSIS_WINDOW_SECONDS, FACE_SAMPLE_INTERVAL, CAPTURE_MAX_SIZE))
    print("  Voix           : %d sous-fenetres | %d Hz" % (VOICE_SUBWINDOWS, SAMPLERATE))
    print("  Seuil          : %.2f" % SEUIL_DISSONANCE_DISTANCE)
    print("  Aucune carte graphique dediee sollicitee (execution CPU).")

    print()
    print("=" * 84)
    print("LATENCE PAR ETAPE, en millisecondes")
    print("=" * 84)
    print("  %-44s %5s %8s %9s %8s %8s"
          % ("etape", "n", "min", "mediane", "p95", "max"))
    for stage, libelle in LIBELLES.items():
        s = resultats.get(stage)
        if not s:
            continue
        print("  %-44s %5d %8.2f %9.2f %8.2f %8.2f"
              % (libelle, s["n"], s["min"], s["mediane"], s["p95"], s["max"]))

    # --- Totaux ------------------------------------------------------------
    print()
    print("=" * 84)
    print("CE QUE LE PRATICIEN ATTEND REELLEMENT")
    print("=" * 84)

    # Coût d'une image de bout en bout : capture, puis chaîne faciale complète.
    # analyze_face_frame englobe déjà MediaPipe et EmotiEffLib, on ne les
    # additionne pas une seconde fois.
    par_image = (resultats.get("capture_hud", {}).get("mediane", 0.0)
                 + resultats.get("analyze_face_frame", {}).get("mediane", 0.0))
    budget = FACE_SAMPLE_INTERVAL * 1000.0
    print()
    print("  1. Chaine faciale, AMORTIE dans la fenetre")
    print("     Le visage est echantillonne pendant l'enregistrement audio : son cout")
    print("     ne s'ajoute au delai que s'il depasse le pas d'echantillonnage.")
    print("     cout median par image : %.1f ms   |   budget disponible : %.0f ms  -> %s"
          % (par_image, budget, "tient" if par_image < budget else "DEBORDE"))
    n_img = int(ANALYSIS_WINDOW_SECONDS / FACE_SAMPLE_INTERVAL)
    print("     occupation du coeur pendant la fenetre : %.1f %% (%d image(s))"
          % (100.0 * par_image * n_img / (ANALYSIS_WINDOW_SECONDS * 1000.0), n_img))

    critique = OrderedDict()
    for k in ("aggregate_face_window", "detect_audio_emotion", "detect_dissonance"):
        if k in resultats:
            critique[k] = resultats[k]
    total_med = sum(v["mediane"] for v in critique.values())
    total_p95 = sum(v["p95"] for v in critique.values())
    if "process_window" in resultats:
        # Mesure directe, preferable a la somme des parties : elle inclut les
        # verifications de rupture de contexte et la gestion du cooldown.
        total_med = resultats["process_window"]["mediane"]
        total_p95 = resultats["process_window"]["p95"]
    ble_med = resultats.get("ble_write", {}).get("mediane", 0.0)
    ble_p95 = resultats.get("ble_write", {}).get("p95", 0.0)

    print()
    print("  2. Chemin critique, APRES la fermeture de la fenetre")
    print("     traitement (decision complete)      : mediane %7.1f ms | p95 %7.1f ms"
          % (total_med, total_p95))
    if ble_med:
        print("     ecriture GATT vers la montre        : mediane %7.1f ms | p95 %7.1f ms"
              % (ble_med, ble_p95))
    else:
        print("     ecriture GATT vers la montre        : non mesuree (--ble, montre requise)")
    print("     TOTAL hors duree de fenetre         : mediane %7.1f ms | p95 %7.1f ms"
          % (total_med + ble_med, total_p95 + ble_p95))

    print()
    print("  3. Delai percu de bout en bout")
    print("     duree de la fenetre d'analyse       : %8.0f ms" % (ANALYSIS_WINDOW_SECONDS * 1000.0))
    print("       (support temporel de la mesure, pas un temps de calcul)")
    print("     + chemin critique (mediane)         : %8.1f ms" % (total_med + ble_med))
    print("     = %.2f s entre la fin d'un comportement et la vibration au poignet."
          % ((ANALYSIS_WINDOW_SECONDS * 1000.0 + total_med + ble_med) / 1000.0))

    # --- Charge ------------------------------------------------------------
    print()
    rss = _memoire_processus_mo()
    if rss:
        print("  Empreinte du processus d'analyse : %.0f Mo de memoire residente" % rss)
    if getattr(args, "_cpu_ratio", None):
        print("  Charge processeur en regime      : %.0f %% d'un coeur, soit %.1f %% "
              "des %s coeurs disponibles"
              % (100.0 * args._cpu_ratio,
                 100.0 * args._cpu_ratio / float(hw["coeurs_logiques"]),
                 hw["coeurs_logiques"]))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"materiel": hw, "backend": runtime_backend(),
                       "config": {"fenetre_s": ANALYSIS_WINDOW_SECONDS,
                                  "pas_image_s": FACE_SAMPLE_INTERVAL,
                                  "capture_px": CAPTURE_MAX_SIZE,
                                  "modele_facial": EMOTIEFFLIB_MODEL,
                                  "gain_va": EMOTIEFFLIB_VA_GAIN},
                       "etapes": resultats}, f, ensure_ascii=False, indent=2)
        print()
        print("  Mesures ecrites dans %s" % args.json)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["etape", "n", "min_ms", "mediane_ms", "p95_ms", "max_ms",
                        "moyenne_ms", "ecart_type_ms"])
            for stage, s in resultats.items():
                w.writerow([LIBELLES[stage].strip(), s["n"]]
                           + [round(s[k], 2) for k in
                              ("min", "mediane", "p95", "max", "moyenne", "ecart_type")])
        print("  Tableau ecrit dans %s" % args.csv)

    return resultats


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", required=True,
                   help="clip fournissant des visages reels et une bande son")
    p.add_argument("--windows", type=int, default=20,
                   help="nombre de fenetres d'analyse a chronometrer")
    p.add_argument("--captures", type=int, default=100,
                   help="nombre de captures d'ecran a chronometrer")
    p.add_argument("--region", default="0,0,640,480",
                   help="zone HUD a capturer : x,y,largeur,hauteur")
    p.add_argument("--warmup", type=int, default=3,
                   help="mesures initiales ecartees (chargement des modeles)")
    p.add_argument("--ble", action="store_true",
                   help="mesure aussi l'ecriture GATT (montre allumee et appairee)")
    p.add_argument("--ble-runs", type=int, default=10)
    p.add_argument("--csv", default=None)
    p.add_argument("--json", default=None)
    args = p.parse_args()

    if not os.path.exists(args.video):
        print("Video introuvable : %s" % args.video)
        return 1

    chrono = Chrono()

    print("Chargement des modeles...", flush=True)
    t0 = time.perf_counter()
    emotion_service.reset_state()
    print("  modeles prets en %.1f s" % (time.perf_counter() - t0))

    # Enveloppes posees sur les objets vivants : le code de production est
    # inchange, seules les frontieres sont chronometrees.
    chrono.wrap(emotion_service._mp_face_detection, "detect", "mediapipe_detect")
    chrono.wrap(emotion_service._emotiefflib, "predict_emotions", "emotiefflib_predict")
    chrono.wrap(emotion_service, "analyze_face_frame", "analyze_face_frame")
    chrono.wrap(emotion_service, "aggregate_face_window", "aggregate_face_window")
    chrono.wrap(emotion_service, "detect_audio_emotion", "detect_audio_emotion")
    chrono.wrap(emotion_service, "detect_dissonance", "detect_dissonance")

    region = tuple(int(v) for v in args.region.split(","))
    print()
    print("Capture d'ecran : %d mesures sur la zone %s..." % (args.captures, region),
          flush=True)
    measure_capture(chrono, region, args.captures)

    n_img_par_fenetre = max(1, int(ANALYSIS_WINDOW_SECONDS / FACE_SAMPLE_INTERVAL))
    besoin = args.windows * n_img_par_fenetre
    print("Chargement de %d image(s) et de la bande son depuis %s..."
          % (besoin, os.path.basename(args.video)), flush=True)
    frames = load_frames(args.video, besoin)
    audio = load_audio(args.video)
    if not frames:
        print("Aucune image exploitable dans la video.")
        return 1
    duree_audio = len(audio) / float(SAMPLERATE)
    print("  %d image(s), %.1f s de son" % (len(frames), duree_audio))

    session = AnalysisSession(emotion_service, warmup_windows=0)
    chrono.wrap(session, "process_window", "process_window")

    n_frames_fenetre = int(ANALYSIS_WINDOW_SECONDS * SAMPLERATE)
    print()
    print("Chronometrage de %d fenetre(s)..." % args.windows, flush=True)
    # Temps processeur cumulé sur tous les threads, rapporté au temps réel :
    # donne la charge en régime sans dépendre d'un échantillonneur externe.
    cpu0, wall0 = time.process_time(), time.perf_counter()
    for w in range(args.windows):
        lot = [frames[(w * n_img_par_fenetre + i) % len(frames)]
               for i in range(n_img_par_fenetre)]
        samples = [s for s in (emotion_service.analyze_face_frame(f) for f in lot) if s]
        # La bande son est parcourue en boucle si le clip est plus court que le
        # nombre de fenetres demande : on mesure un cout de calcul, pas un
        # contenu, et l'inference vocale ne depend que de la taille du bloc.
        debut = (w * n_frames_fenetre) % max(1, len(audio) - n_frames_fenetre or 1)
        bloc = audio[debut:debut + n_frames_fenetre]
        if len(bloc) < n_frames_fenetre:
            bloc = np.pad(bloc, (0, n_frames_fenetre - len(bloc)))
        session.process_window(samples, bloc, SAMPLERATE)
        print("  fenetre %d/%d" % (w + 1, args.windows), flush=True)
    # Le banc enchaîne les fenêtres sans temps mort, alors qu'une séance réelle
    # en traite une toutes les ANALYSIS_WINDOW_SECONDS. Rapporter le temps
    # processeur au temps du banc surestimerait donc la charge d'un facteur
    # cinq : on le rapporte à la durée réelle d'une fenêtre.
    cpu_par_fenetre = (time.process_time() - cpu0) / max(1, args.windows)
    args._cpu_ratio = cpu_par_fenetre / ANALYSIS_WINDOW_SECONDS
    args._bench_wall = time.perf_counter() - wall0

    if args.ble:
        print()
        print("Mesure de l'ecriture GATT (%d envois espaces de 3 s)..." % args.ble_runs,
              flush=True)
        measure_ble(chrono, args.ble_runs)

    chrono.drop_warmup(args.warmup)
    report(chrono, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
