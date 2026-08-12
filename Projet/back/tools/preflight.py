"""
Contrôle avant démonstration.

Vérifie, dans l'ordre, tout ce qui peut faire échouer une démonstration en
direct : dépendances, modèles, périphérique audio, montre, cohérence de la
configuration. Chaque point est vert, orange ou rouge, avec la commande de
correction quand il y en a une.

À lancer une fois la veille, et une fois juste avant de passer.

    python -m tools.preflight
    python -m tools.preflight --sans-ble      # si la montre n'est pas allumée
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

VERT, ORANGE, ROUGE = "  [ OK ]", "  [ !  ]", "  [FAIL]"
_bilan = {"ok": 0, "avert": 0, "echec": 0}


def ok(msg, detail=""):
    _bilan["ok"] += 1
    print("%s %s%s" % (VERT, msg, ("  (" + detail + ")") if detail else ""), flush=True)


def avert(msg, correction=""):
    _bilan["avert"] += 1
    print("%s %s" % (ORANGE, msg), flush=True)
    if correction:
        print("         -> %s" % correction, flush=True)


def echec(msg, correction=""):
    _bilan["echec"] += 1
    print("%s %s" % (ROUGE, msg), flush=True)
    if correction:
        print("         -> %s" % correction, flush=True)


def section(titre):
    print()
    print(titre)
    print("-" * len(titre))


def verifier_dependances():
    section("1. Dépendances")
    manquants = []
    for module, paquet in [("cv2", "opencv-python"), ("numpy", "numpy"),
                           ("mediapipe", "mediapipe"), ("emotiefflib", "emotiefflib"),
                           ("onnxruntime", "onnxruntime"), ("torch", "torch"),
                           ("transformers", "transformers"), ("librosa", "librosa"),
                           ("soundcard", "soundcard"), ("mss", "mss"),
                           ("fastapi", "fastapi"), ("uvicorn", "uvicorn")]:
        try:
            __import__(module)
        except ImportError:
            manquants.append(paquet)
    if manquants:
        echec("modules absents : %s" % ", ".join(manquants),
              "activez le venv, puis pip install -r requirements.txt")
        return False
    ok("tous les modules sont importables")
    try:
        import bleak  # noqa: F401
        ok("bleak présent (montre disponible)")
    except ImportError:
        avert("bleak absent : l'analyse tournera, la vibration non",
              "pip install bleak")
    return True


def verifier_configuration():
    section("2. Cohérence de la configuration")
    from config import settings as S

    print("     fenêtre d'analyse           : %.1f s" % S.ANALYSIS_WINDOW_SECONDS)
    print("     échantillonnage visage      : %.2f s" % S.FACE_SAMPLE_INTERVAL)
    print("     seuil de dissonance         : %.2f" % S.SEUIL_DISSONANCE_DISTANCE)
    print("     sous-fenêtre vocale min.    : %.2f s" % S.VOICE_SUBWINDOW_MIN_SECONDS)
    print()

    images = int(S.ANALYSIS_WINDOW_SECONDS / S.FACE_SAMPLE_INTERVAL)
    if images < S.FACE_MIN_SAMPLES:
        echec("au mieux %d image(s) par fenêtre pour un minimum de %d : aucune fenêtre exploitable"
              % (images, S.FACE_MIN_SAMPLES),
              "baissez FACE_SAMPLE_INTERVAL ou FACE_MIN_SAMPLES")
    else:
        ok("%d images par fenêtre (minimum %d)" % (images, S.FACE_MIN_SAMPLES))

    # Le découpage vocal doit permettre au moins deux sous-fenêtres, faute de quoi
    # la fiabilité par concordance est impossible et le service retombe
    # silencieusement sur l'ancien mode « intensité ».
    total = S.ANALYSIS_WINDOW_SECONDS
    n = max(1, S.VOICE_SUBWINDOWS)
    sub = 2 * total / (n + 1)
    if S.VOICE_CONFIDENCE_MODE == "stabilite" and (
            n < 2 or sub < S.VOICE_SUBWINDOW_MIN_SECONDS or total < 2 * S.VOICE_SUBWINDOW_MIN_SECONDS):
        avert("le mode vocal « stabilité » ne tiendra pas : sous-fenêtres de %.2f s "
              "pour un minimum de %.2f s. Retour silencieux au mode « intensité »."
              % (sub, S.VOICE_SUBWINDOW_MIN_SECONDS),
              "VOICE_SUBWINDOW_MIN_SECONDS=%.1f dans le .env" % max(0.3, sub * 0.8))
    else:
        ok("découpage vocal cohérent (%d sous-fenêtres de %.2f s)" % (n, sub))

    # Les seuils ont été calibrés sur la fenêtre de production. Les mesurer à une
    # autre échelle changerait la grandeur des distances et rendrait les seuils
    # inapplicables.
    FENETRE_CALIBRATION = 3.0
    if abs(S.ANALYSIS_WINDOW_SECONDS - FENETRE_CALIBRATION) > 0.01:
        avert("le seuil %.2f a été calibré sur une fenêtre de %.1f s, la session "
              "tourne à %.1f s : les distances ne sont pas comparables"
              % (S.SEUIL_DISSONANCE_DISTANCE, FENETRE_CALIBRATION,
                 S.ANALYSIS_WINDOW_SECONDS),
              "retirez ANALYSIS_WINDOW_SECONDS du .env pour revenir à %.1f s"
              % FENETRE_CALIBRATION)
    else:
        ok("fenêtre alignée sur la calibration (%.1f s)" % FENETRE_CALIBRATION)


def verifier_modeles():
    section("3. Modèles")
    chemin = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "models", "face_detector.task")
    if not os.path.exists(chemin):
        echec("modèle MediaPipe absent", "python download_model.py")
        return
    ok("modèle MediaPipe présent", "%.0f Ko" % (os.path.getsize(chemin) / 1024))

    print("     chargement des modèles (peut prendre une minute au premier lancement)…",
          flush=True)
    t0 = time.time()
    try:
        from services.emotion_service import emotion_service
    except Exception as e:
        echec("échec du chargement : %s" % e)
        return
    duree = time.time() - t0
    ok("modèle facial EmotiEffLib chargé")
    if getattr(emotion_service, "_voice_pipeline", None):
        ok("modèle vocal wav2vec2 chargé", "%.0f s au total" % duree)
    else:
        echec("modèle vocal indisponible : aucune dissonance ne pourra être calculée",
              "vérifiez la connexion réseau au premier lancement (téléchargement ~1 Go)")


def verifier_audio():
    section("4. Capture audio (loopback)")
    try:
        import soundcard as sc
        import numpy as np
        from config.settings import AUDIO_DEVICE, SAMPLERATE
    except Exception as e:
        echec("import impossible : %s" % e)
        return

    try:
        nom = AUDIO_DEVICE or str(sc.default_speaker().name)
    except Exception as e:
        echec("aucun haut-parleur détecté : %s" % e)
        return
    print("     périphérique : %s" % nom)
    print("     >>> LANCEZ UNE VIDÉO AVEC DU SON MAINTENANT, mesure dans 2 s…", flush=True)
    time.sleep(2)
    try:
        mic = sc.get_microphone(id=nom, include_loopback=True)
        with mic.recorder(samplerate=SAMPLERATE) as rec:
            data = rec.record(numframes=SAMPLERATE)
        rms = float(np.sqrt(np.mean(np.square(data.astype(np.float32)))))
    except Exception as e:
        echec("capture impossible sur ce périphérique : %s" % e,
              "choisissez-en un autre dans les paramètres du HUD")
        return

    if rms < 0.001:
        echec("aucun son capté (RMS %.5f)" % rms,
              "le son ne sort pas de ce périphérique : essayez la sortie interne "
              "(ex. Realtek Digital Output) dans les paramètres du HUD")
    elif rms < 0.01:
        avert("son très faible (RMS %.4f) : le rejet du silence risque de s'activer" % rms,
              "montez le volume système")
    else:
        ok("son capté correctement", "RMS %.3f" % rms)


def verifier_ble():
    section("5. Montre connectée")
    try:
        import asyncio
        from services.ble_service import ble_service
        from config.settings import MAC_MONTRE
    except Exception as e:
        avert("service BLE indisponible : %s" % e)
        return
    print("     adresse configurée : %s" % MAC_MONTRE)
    try:
        connecte = asyncio.run(ble_service.connect(sync_time=False))
    except Exception as e:
        avert("connexion impossible : %s" % e, "montre allumée ? Bluetooth activé ?")
        return
    if not connecte:
        avert("montre injoignable", "allumez-la, rapprochez-la, relancez")
        return
    ok("montre connectée")
    try:
        asyncio.run(ble_service.vibrate())
        ok("vibration de test envoyée", "vérifiez au poignet")
        asyncio.run(ble_service.disconnect())
    except Exception as e:
        avert("vibration impossible : %s" % e)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sans-ble", action="store_true", help="ignore la montre")
    p.add_argument("--rapide", action="store_true",
                   help="ignore le chargement des modèles et la montre")
    args = p.parse_args()

    print("=" * 66)
    print("CONTRÔLE AVANT DÉMONSTRATION | Under")
    print("=" * 66)

    if not verifier_dependances():
        print()
        print("Dépendances manquantes : le reste n'a pas de sens.")
        return 1
    verifier_configuration()
    if not args.rapide:
        verifier_modeles()
    verifier_audio()
    if not args.sans_ble and not args.rapide:
        verifier_ble()

    print()
    print("=" * 66)
    print("  %d point(s) conformes | %d avertissement(s) | %d échec(s)"
          % (_bilan["ok"], _bilan["avert"], _bilan["echec"]))
    if _bilan["echec"]:
        print("  Des échecs bloquants subsistent : corrigez-les avant de passer.")
    elif _bilan["avert"]:
        print("  Aucun blocage. Les avertissements dégradent la qualité sans empêcher la démo.")
    else:
        print("  Tout est vert.")
    print("=" * 66)
    return 1 if _bilan["echec"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
