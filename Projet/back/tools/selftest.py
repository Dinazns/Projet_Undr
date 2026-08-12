"""
Test de bout en bout : la vidéo joue à l'écran, le dispositif la regarde.

C'est le seul banc du dépôt qui exerce la chaîne COMPLÈTE, y compris les deux
entrées que tous les autres court-circuitent : les pixels de l'écran et le son
du haut-parleur capté en loopback. Il joue le fichier dans une fenêtre, envoie
sa bande son sur la sortie par défaut, puis analyse cette fenêtre exactement
comme la boucle d'api.main analyserait la visio d'un patient.

Comparer sa trace à celle de tools/replay.py sur le même fichier isole en une
lecture ce que la chaîne d'acquisition coûte par rapport à la lecture directe
du fichier.

    python -m tools.selftest --video ../../Video/generated_video.mp4 --tours 3

ATTENTION : ouvre une fenêtre et joue du son. Ne rien faire d'autre pendant la
mesure, toute fenêtre passant par-dessus serait analysée à la place de la vidéo.
"""
import argparse
import os
import sys
import threading
import time
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from config.settings import (  # noqa: E402
    ANALYSIS_WINDOW_SECONDS,
    AUDIO_DEVICE,
    FACE_SAMPLE_INTERVAL,
    SAMPLERATE,
    SEUIL_DISSONANCE_DISTANCE,
)
from services.analysis_session import AnalysisSession  # noqa: E402
from services.emotion_service import emotion_service  # noqa: E402
from tools.evaluate_corpus import load_audio  # noqa: E402

FENETRE = "Undr - test de bout en bout"


def dessiner_hud(image: np.ndarray, mode: str) -> np.ndarray:
    """
    Superpose ce que le HUD dessine par-dessus la visio.

    La zone envoyée au backend est celle de la fenêtre HUD, et mss capture le
    bureau composité : tout ce que l'interface affiche se retrouve donc dans
    l'image analysée. Reproduire ces calques ici est le seul moyen de savoir ce
    qu'ils coûtent à la détection.
    """
    if mode == "aucun":
        return image
    img = image.copy()
    h, w = img.shape[:2]

    # .capture-frame : bordure de 2 px, inset 4 px, couleur #deff9a.
    cv2.rectangle(img, (4, 4), (w - 5, h - 5), (154, 255, 222), 2)

    if mode in ("widget", "tout"):
        # .mini-widget : panneau vitre, top 16 right 16, fond noir a 65 %.
        lw, lh = 300, 44
        x1, y1 = w - 16 - lw, 16
        bloc = img[y1:y1 + lh, x1:x1 + lw]
        # backdrop-filter: blur(16px) puis fond rgba(15,15,15,0.65)
        flou = cv2.GaussianBlur(bloc, (0, 0), 8)
        img[y1:y1 + lh, x1:x1 + lw] = cv2.addWeighted(
            flou, 0.35, np.full_like(bloc, 15), 0.65, 0)

    if mode in ("parametres", "tout"):
        # .settings-overlay : inset 0, rgba(0,0,0,0.5) sur TOUTE la zone,
        # plus le panneau de 300 px de large au centre.
        img = cv2.addWeighted(img, 0.5, np.zeros_like(img), 0.5, 0)
        pw, ph = 300, 420
        x1, y1 = (w - pw) // 2, max(0, (h - ph) // 2)
        y2 = min(h, y1 + ph)
        bloc = img[y1:y2, x1:x1 + pw]
        img[y1:y2, x1:x1 + pw] = cv2.addWeighted(
            cv2.GaussianBlur(bloc, (0, 0), 8), 0.35,
            np.full_like(bloc, 15), 0.65, 0)
    return img


_stop = threading.Event()
_resultats: List[dict] = []
_zone: Optional[Tuple[int, int, int, int]] = None


def jouer_son(audio: np.ndarray, tours: int) -> None:
    """Envoie la bande son sur la sortie par défaut, que le loopback capte."""
    import soundcard as sc
    try:
        hp = sc.default_speaker()
        with hp.player(samplerate=SAMPLERATE) as lecteur:
            for _ in range(tours):
                if _stop.is_set():
                    return
                lecteur.play(audio)
    except Exception as exc:
        print("  Lecture audio impossible : %s" % exc)


def analyser(duree: float) -> None:
    """
    Boucle d'analyse, identique à celle d'api.main.

    Le visage est échantillonné PENDANT l'enregistrement audio : la capture
    d'écran part dans ce thread pendant que l'enregistrement bloque, ce qui
    reproduit le parallélisme de la boucle réelle sans asyncio.
    """
    import soundcard as sc
    from utils.screen_capture import ScreenCapture

    while _zone is None and not _stop.is_set():
        time.sleep(0.05)
    if _stop.is_set():
        return

    capture = ScreenCapture()
    capture.set_hud_coords(*_zone)
    peripherique = AUDIO_DEVICE or str(sc.default_speaker().name)
    micro = sc.get_microphone(id=peripherique, include_loopback=True)
    session = AnalysisSession(emotion_service)
    n_ech = int(SAMPLERATE * ANALYSIS_WINDOW_SECONDS)

    print("  Zone analysee : %s | peripherique : %s" % (_zone, peripherique))
    print()
    print("  %-7s %4s %-21s %-21s %8s %-10s %s"
          % ("fenetre", "img", "visage", "voix", "distance", "niveau", "montre"))

    images: List[dict] = []
    verrou = threading.Lock()

    def echantillonner(stop_at: float) -> None:
        prochaine = time.monotonic()
        while time.monotonic() < stop_at and not _stop.is_set():
            if time.monotonic() >= prochaine:
                frame = capture.capture_hud_array()
                if frame is not None:
                    s = emotion_service.analyze_face_frame(frame)
                    if s:
                        with verrou:
                            images.append(s)
                prochaine += FACE_SAMPLE_INTERVAL
            time.sleep(0.01)

    fin = time.monotonic() + duree
    index = 0
    with micro.recorder(samplerate=SAMPLERATE) as enregistreur:
        while time.monotonic() < fin and not _stop.is_set():
            with verrou:
                images.clear()
            t_fin = time.monotonic() + ANALYSIS_WINDOW_SECONDS
            th = threading.Thread(target=echantillonner, args=(t_fin,), daemon=True)
            th.start()
            audio = enregistreur.record(numframes=n_ech)
            th.join(timeout=1.0)
            with verrou:
                lot = list(images)

            if audio.ndim > 1:
                audio = np.mean(audio, axis=1)
            out = session.process_window(lot, audio, SAMPLERATE)

            if out.evaluated:
                print("  %-7s %4d %-21s %-21s %8.2f %-10s %s"
                      % ("#%d" % index, out.n_face_samples,
                         "%s (%.0f)" % (out.face_emotion, out.face_score),
                         "%s (%.0f)" % (out.voice_emotion, out.voice_score),
                         out.emotion_distance, out.alert_level,
                         "VIBRE" if out.should_vibrate else ""), flush=True)
            else:
                print("  %-7s %4d -- ecartee : %s"
                      % ("#%d" % index, out.n_face_samples, out.skipped), flush=True)

            _resultats.append({
                "fenetre": index,
                "evaluee": out.evaluated,
                "ecartee": out.skipped or "",
                "images": out.n_face_samples,
                "visage": out.face_emotion or "",
                "visage_v": out.face_coords[0] if out.face_coords else None,
                "visage_a": out.face_coords[1] if out.face_coords else None,
                "voix": out.voice_emotion or "",
                "voix_v": out.voice_coords[0] if out.voice_coords else None,
                "voix_a": out.voice_coords[1] if out.voice_coords else None,
                "distance": out.emotion_distance,
                "niveau": out.alert_level,
                "vibration": out.should_vibrate,
            })
            index += 1
    _stop.set()


def main() -> int:
    global _zone

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--video", required=True)
    p.add_argument("--tours", type=int, default=3,
                   help="nombre de lectures enchainees du fichier")
    p.add_argument("--largeur", type=int, default=960,
                   help="largeur de la fenetre de lecture, en pixels")
    p.add_argument("--hud", choices=("aucun", "widget", "parametres", "tout"),
                   default="aucun",
                   help="superpose les calques du HUD sur la video, comme ils se "
                        "presentent dans la zone reellement capturee. « widget » : le "
                        "panneau en haut a droite. « parametres » : le voile noir a "
                        "50 %% du panneau de reglages. « tout » : les deux.")
    p.add_argument("--csv", default=None)
    args = p.parse_args()

    if not os.path.exists(args.video):
        print("Introuvable : %s" % args.video)
        return 1

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    if not frames:
        print("Aucune image lisible.")
        return 1

    audio = load_audio(args.video)
    h0, w0 = frames[0].shape[:2]
    echelle = args.largeur / float(w0)
    taille = (int(w0 * echelle), int(h0 * echelle))
    duree_video = len(frames) / fps

    print("TEST DE BOUT EN BOUT : la video joue a l'ecran, le dispositif la regarde.")
    print("  Fichier : %s" % os.path.basename(args.video))
    print("  %d image(s) a %.1f i/s, soit %.1f s | %d tour(s) = %.0f s"
          % (len(frames), fps, duree_video, args.tours, duree_video * args.tours))
    print("  Affichage %dx%d | fenetre d'analyse %.1f s"
          % (taille[0], taille[1], ANALYSIS_WINDOW_SECONDS))
    print("  Ne rien faire d'autre pendant la mesure.")
    print()

    cv2.namedWindow(FENETRE, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(FENETRE, taille[0], taille[1])
    cv2.moveWindow(FENETRE, 60, 60)
    cv2.imshow(FENETRE, dessiner_hud(cv2.resize(frames[0], taille), args.hud))
    cv2.waitKey(400)

    try:
        x, y, w, h = cv2.getWindowImageRect(FENETRE)
        if w > 0 and h > 0:
            _zone = (x, y, w, h)
    except Exception:
        pass
    if _zone is None:
        _zone = (68, 100, taille[0], taille[1])
        print("  Rectangle de fenetre indisponible : zone estimee.")

    duree_totale = duree_video * args.tours
    threading.Thread(target=jouer_son, args=(audio, args.tours), daemon=True).start()
    threading.Thread(target=analyser, args=(duree_totale,), daemon=True).start()

    # Lecture dans le thread principal : HighGUI n'aime pas etre pilote ailleurs.
    debut = time.monotonic()
    while not _stop.is_set():
        ecoule = time.monotonic() - debut
        if ecoule >= duree_totale:
            break
        idx = int((ecoule % duree_video) * fps)
        if idx >= len(frames):
            idx = len(frames) - 1
        cv2.imshow(FENETRE, dessiner_hud(cv2.resize(frames[idx], taille), args.hud))
        if cv2.waitKey(max(1, int(1000 / fps / 2))) == 27:
            break
    _stop.set()
    time.sleep(0.3)
    cv2.destroyAllWindows()
    cv2.waitKey(1)

    ev = [r for r in _resultats if r["evaluee"]]
    alertes = [r for r in ev if r["niveau"] != "NONE"]
    vibrations = [r for r in ev if r["vibration"]]
    print()
    print("-" * 88)
    print("  %d fenetre(s) | %d evaluee(s) | %d alerte(s) | %d VIBRATION(S)"
          % (len(_resultats), len(ev), len(alertes), len(vibrations)))
    if len(_resultats) > len(ev):
        motifs = {}
        for r in _resultats:
            if not r["evaluee"]:
                motifs[r["ecartee"]] = motifs.get(r["ecartee"], 0) + 1
        print("  ecartees : %s" % ", ".join("%s=%d" % kv for kv in sorted(motifs.items())))
    if ev:
        d = sorted(r["distance"] for r in ev)
        print("  distance : min %.2f | mediane %.2f | max %.2f  (seuil %.2f)"
              % (d[0], d[len(d) // 2], d[-1], SEUIL_DISSONANCE_DISTANCE))

    if args.csv and _resultats:
        import csv as _csv
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = _csv.DictWriter(f, fieldnames=list(_resultats[0].keys()))
            w.writeheader()
            w.writerows(_resultats)
        print("  Trace ecrite dans %s" % args.csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
