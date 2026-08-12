"""
Banc d'évaluation hors ligne sur corpus vidéo.

Fait tourner la chaîne d'analyse réelle (AnalysisSession, donc exactement la
logique de décision utilisée en séance) sur des fichiers vidéo, sans HUD, sans
Electron et sans capture d'écran. Résultats reproductibles par un tiers.

Deux modes, correspondant à deux questions différentes :

  --mode congruence
      Chaque clip est joué tel quel. Dans RAVDESS, l'acteur exprime la MÊME
      émotion sur le visage et dans la voix : les deux canaux sont congruents.
      Toute alerte est donc un FAUX POSITIF. Ce mode mesure la spécificité.

  --mode croise
      Le visage d'un clip est associé à la bande son d'un autre clip du même
      acteur, même phrase, mais d'émotion opposée. On obtient une dissonance
      de synthèse à vérité terrain connue. Ce mode mesure la sensibilité.
      Il construit le stimulus qui manque à l'état de l'art : les corpus
      publics annotent une émotion congruente par extrait, aucun n'annote une
      incongruence ENTRE canaux.

Limite à déclarer dans toute exploitation de ces chiffres : les émotions de
RAVDESS sont JOUÉES par des comédiens, en studio, sans compression de
visioconférence. Elles ne préjugent pas du comportement du dispositif sur des
expressions spontanées en téléconsultation.

Exemples
--------
    python -m tools.evaluate_corpus --corpus ../../Actor_04 --mode congruence
    python -m tools.evaluate_corpus --corpus ../../Actor_04 --mode croise --degrade
    python -m tools.evaluate_corpus --corpus ../../Actor_04 --mode congruence --csv resultats.csv
"""
import argparse
import csv
import itertools
import logging
import os
import random
import shutil
import subprocess
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (  # noqa: E402
    ANALYSIS_WINDOW_SECONDS,
    CAPTURE_MAX_SIZE,
    FACE_SAMPLE_INTERVAL,
    SAMPLERATE,
    SEUIL_DISSONANCE_DISTANCE,
    VOICE_SUBWINDOW_MIN_SECONDS,
)
# Import direct des sous-modules : le paquet services/ tire aussi le service
# BLE, donc bleak, dont l'évaluation hors ligne n'a aucun besoin.
from services.analysis_session import AnalysisSession  # noqa: E402
from services.emotion_service import emotion_service  # noqa: E402

logger = logging.getLogger("evaluate_corpus")

# --- Nomenclature RAVDESS --------------------------------------------------
# 01-01-06-01-02-01-12.mp4
#  |  |  |  |  |  |  +-- acteur (01-24 ; impair = homme, pair = femme)
#  |  |  |  |  |  +----- répétition
#  |  |  |  |  +-------- phrase (01 "Kids are talking...", 02 "Dogs are sitting...")
#  |  |  |  +----------- intensité (01 normale, 02 forte)
#  |  |  +-------------- émotion
#  |  +----------------- canal vocal (01 parole, 02 chant)
#  +-------------------- modalité (01 audio+vidéo, 02 vidéo seule, 03 audio seul)
EMOTIONS = {
    "01": "neutre", "02": "calme", "03": "joie", "04": "tristesse",
    "05": "colère", "06": "peur", "07": "dégoût", "08": "surprise",
}
# Valence attendue de chaque émotion jouée, pour former des paires opposées.
VALENCE = {
    "neutre": 0, "calme": 1, "joie": 1,
    "tristesse": -1, "colère": -1, "peur": -1, "dégoût": -1, "surprise": 0,
}


class Clip:
    __slots__ = ("path", "modality", "emotion", "intensity", "statement", "repetition", "actor")

    def __init__(self, path: str):
        parts = os.path.basename(path)[:-4].split("-")
        self.path = path
        self.modality, _, emo, self.intensity, self.statement, self.repetition, self.actor = parts
        self.emotion = EMOTIONS.get(emo, emo)

    @property
    def has_audio(self) -> bool:
        # La modalité 02 est « vidéo seule » : la piste audio existe mais elle
        # est vide. Ces fichiers ne peuvent produire aucune fenêtre exploitable.
        return self.modality == "01"

    def __repr__(self):
        return "%s[%s/%s]" % (os.path.basename(self.path), self.emotion, self.intensity)


def find_clips(corpus_dir: str) -> Tuple[List[Clip], List[Clip]]:
    clips, silent = [], []
    for name in sorted(os.listdir(corpus_dir)):
        if not name.lower().endswith(".mp4"):
            continue
        try:
            clip = Clip(os.path.join(corpus_dir, name))
        except ValueError:
            logger.warning("Nom hors nomenclature RAVDESS, ignoré : %s", name)
            continue
        (clips if clip.has_audio else silent).append(clip)
    return clips, silent


# --- Extraction audio ------------------------------------------------------

def _ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise SystemExit(
            "ffmpeg est introuvable. Installez-le, ou bien : pip install imageio-ffmpeg"
        )


def speech_span(audio: np.ndarray, sample_rate: int = SAMPLERATE,
                frame: float = 0.1, threshold: float = 0.01) -> Tuple[float, float]:
    """
    Bornes de la partie parlée, en secondes.

    Les extraits de RAVDESS sont encadrés d'environ une seconde de silence de
    part et d'autre, pour une parole utile d'à peine plus d'une seconde. Placer
    les fenêtres sans tenir compte de ce cadrage revient à analyser du silence :
    la moitié des fenêtres est alors écartée, et les autres diluent la prosodie
    dans du blanc.
    """
    step = int(frame * sample_rate)
    if step <= 0 or audio.size < step:
        return 0.0, audio.size / float(sample_rate)
    energies = np.array([
        np.sqrt(np.mean(audio[i:i + step] ** 2)) for i in range(0, audio.size - step, step)
    ])
    active = np.where(energies > threshold)[0]
    if active.size == 0:
        return 0.0, audio.size / float(sample_rate)
    return float(active[0] * frame), float((active[-1] + 1) * frame)


def load_audio(path: str, sample_rate: int = SAMPLERATE) -> np.ndarray:
    """Piste audio en mono float32 au débit attendu par le modèle vocal."""
    out = subprocess.run(
        [_ffmpeg_exe(), "-v", "quiet", "-i", path, "-ac", "1",
         "-ar", str(sample_rate), "-f", "f32le", "-"],
        capture_output=True, check=False,
    ).stdout
    return np.frombuffer(out, dtype=np.float32).copy()


# --- Échantillonnage vidéo -------------------------------------------------

def _prepare_frame(frame: np.ndarray, degrade: bool) -> np.ndarray:
    """
    Reproduit ce que subit l'image dans la chaîne réelle.

    Réduction à CAPTURE_MAX_SIZE comme le fait capture_hud_array(). Avec
    --degrade, on ajoute un aller-retour JPEG pour approcher la dégradation
    d'un flux de visioconférence : sans lui, les mesures sont faites sur des
    images de studio et surestiment les performances.
    """
    h, w = frame.shape[:2]
    longest = max(h, w)
    if longest > CAPTURE_MAX_SIZE:
        s = CAPTURE_MAX_SIZE / float(longest)
        frame = cv2.resize(frame, (max(1, int(w * s)), max(1, int(h * s))),
                           interpolation=cv2.INTER_AREA)
    if degrade:
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 55])
        if ok:
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return frame


def analyse_frames(video_path: str, degrade: bool) -> List[Tuple[float, dict]]:
    """
    Analyse les images du clip une seule fois et renvoie (instant, échantillon).

    Une image toutes les FACE_SAMPLE_INTERVAL secondes, exactement comme
    _sample_face_window() le fait en direct sur la capture d'écran. Les fenêtres
    pouvant se recouvrir, chaque image est analysée une fois et réutilisée par
    toutes les fenêtres qui la contiennent.
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(1, int(round(fps * FACE_SAMPLE_INTERVAL)))
    out: List[Tuple[float, dict]] = []

    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % stride == 0:
            sample = emotion_service.analyze_face_frame(_prepare_frame(frame, degrade))
            if sample:
                out.append((idx / fps, sample))
        idx += 1
    cap.release()
    return out


# --- Évaluation d'un couple (vidéo, audio) --------------------------------

def evaluate_pair(
    video_path: str, audio: np.ndarray, degrade: bool,
    window: float, hop: float, warmup: Optional[int], align_speech: bool = True,
) -> List[dict]:
    """Fait tourner la chaîne réelle sur un couple vidéo/audio et renvoie les fenêtres."""
    frames = analyse_frames(video_path, degrade)
    duration = len(audio) / float(SAMPLERATE)

    # Fenêtres glissantes, cadrées sur la parole. Les extraits de RAVDESS durent
    # environ 4 s dont à peine plus d'une de parole : sans recouvrement ni
    # cadrage, chaque clip ne produirait qu'un point de mesure, largement
    # rempli de silence.
    lo, hi = (0.0, duration)
    if align_speech:
        lo, hi = speech_span(audio)
        lo = max(0.0, lo - 0.15)
        hi = min(duration, hi + 0.15)

    starts = []
    t = lo
    while t + window <= hi + 1e-6:
        starts.append(t)
        t += hop
    if not starts:
        # La parole est plus courte que la fenêtre : on centre une fenêtre unique
        # sur le segment parlé plutôt que de ne rien mesurer.
        starts = [max(0.0, min(duration - window, (lo + hi) / 2.0 - window / 2.0))]

    # Session neuve par clip : la dernière fenêtre du clip précédent ne peut pas
    # contaminer la première du suivant, exactement comme au changement de scène.
    session = AnalysisSession(emotion_service, warmup_windows=warmup)

    rows = []
    for w, start in enumerate(starts):
        a0, a1 = int(start * SAMPLERATE), int((start + window) * SAMPLERATE)
        chunk = audio[a0:a1]
        if len(chunk) < int(window * SAMPLERATE) // 2:
            continue
        face_samples = [s for (ts, s) in frames if start <= ts < start + window]
        out = session.process_window(face_samples, chunk, SAMPLERATE)
        rows.append({
            "debut_s": round(start, 2),
            "fenetre": w,
            "evaluee": out.evaluated,
            "ecartee": out.skipped or "",
            "images_visage": out.n_face_samples,
            "dispersion": round(out.face_dispersion, 3) if out.face_dispersion is not None else "",
            "visage": out.face_emotion or "",
            "fiab_visage": round(out.face_score, 1),
            "voix": out.voice_emotion or "",
            "fiab_voix": round(out.voice_score, 1),
            "sous_fenetres_voix": out.voice_subwindows,
            "distance": round(out.emotion_distance, 3),
            "niveau": out.alert_level,
            "score": round(out.confidence, 1),
            "vibration": out.should_vibrate,
        })
    return rows


# --- Modes ----------------------------------------------------------------

def run_congruence(clips: List[Clip], degrade: bool, limit: Optional[int],
                   window: float, hop: float, warmup: Optional[int],
                   align_speech: bool = True) -> List[dict]:
    rows = []
    todo = clips[:limit] if limit else clips
    for i, clip in enumerate(todo, 1):
        print("  [%3d/%d] %s" % (i, len(todo), os.path.basename(clip.path)), flush=True)
        audio = load_audio(clip.path)
        for r in evaluate_pair(clip.path, audio, degrade, window, hop, warmup, align_speech):
            r.update(fichier=os.path.basename(clip.path), emotion=clip.emotion,
                     intensite=clip.intensity, attendu="congruent")
            rows.append(r)
    return rows


def build_opposite_pairs(clips: List[Clip], limit: Optional[int], seed: int) -> List[Tuple[Clip, Clip]]:
    """
    Associe des clips de valence opposée, à phrase identique.

    Même acteur, même phrase, même intensité si possible : seule l'émotion
    change. Le visage vient du premier, la voix du second.
    """
    pairs = []
    by_statement: Dict[str, List[Clip]] = defaultdict(list)
    for c in clips:
        by_statement[c.statement].append(c)
    for statement, group in by_statement.items():
        pos = [c for c in group if VALENCE.get(c.emotion, 0) > 0]
        neg = [c for c in group if VALENCE.get(c.emotion, 0) < 0]
        for a, b in itertools.product(pos, neg):
            pairs.append((a, b))   # visage positif / voix négative
            pairs.append((b, a))   # visage négatif / voix positive
    random.Random(seed).shuffle(pairs)
    return pairs[:limit] if limit else pairs


def run_croise(clips: List[Clip], degrade: bool, limit: Optional[int], seed: int,
               window: float, hop: float, warmup: Optional[int],
               align_speech: bool = True) -> List[dict]:
    pairs = build_opposite_pairs(clips, limit, seed)
    rows = []
    for i, (face_clip, voice_clip) in enumerate(pairs, 1):
        print("  [%3d/%d] visage=%s  voix=%s"
              % (i, len(pairs), face_clip.emotion, voice_clip.emotion), flush=True)
        audio = load_audio(voice_clip.path)
        for r in evaluate_pair(face_clip.path, audio, degrade, window, hop, warmup, align_speech):
            r.update(fichier="%s | %s" % (os.path.basename(face_clip.path),
                                          os.path.basename(voice_clip.path)),
                     emotion="%s/%s" % (face_clip.emotion, voice_clip.emotion),
                     intensite=face_clip.intensity, attendu="dissonant")
            rows.append(r)
    return rows


# --- Restitution -----------------------------------------------------------

def summarise(rows: List[dict], mode: str) -> None:
    ev = [r for r in rows if r["evaluee"]]
    alerts = [r for r in ev if r["niveau"] != "NONE"]
    vibr = [r for r in ev if r["vibration"]]

    print()
    print("=" * 74)
    print("SYNTHÈSE | mode %s" % mode)
    print("=" * 74)
    print("  fenêtres produites          : %d" % len(rows))
    print("  fenêtres évaluées           : %d (%.0f %%)"
          % (len(ev), 100 * len(ev) / max(len(rows), 1)))

    ecartees = defaultdict(int)
    for r in rows:
        if not r["evaluee"]:
            ecartees[r["ecartee"]] += 1
    if ecartees:
        print("  écartées :", ", ".join("%s=%d" % kv for kv in sorted(ecartees.items())))

    label = "FAUX POSITIFS" if mode == "congruence" else "DÉTECTIONS"
    print()
    print("  %s : %d / %d fenêtres évaluées (%.1f %%)"
          % (label, len(alerts), len(ev), 100 * len(alerts) / max(len(ev), 1)))
    print("  dont déclenchant une vibration : %d" % len(vibr))
    niveaux = defaultdict(int)
    for r in alerts:
        niveaux[r["niveau"]] += 1
    if niveaux:
        print("  répartition :", ", ".join("%s=%d" % kv for kv in sorted(niveaux.items())))

    mono = [r for r in ev if r.get("sous_fenetres_voix", 0) < 2]
    if mono:
        print()
        print("  ATTENTION : %d fenêtre(s) évaluée(s) sur %d n'ont produit qu'une seule"
              % (len(mono), len(ev)))
        print("  sous-fenêtre vocale. En dessous de deux, la fiabilité par concordance")
        print("  est impossible et le service retombe sur l'ancien mode « intensité ».")
        print("  Allonger --window, ou baisser VOICE_SUBWINDOW_MIN_SECONDS.")

    d = np.array([r["distance"] for r in ev], dtype=float)
    if d.size:
        print()
        print("  distance visage/voix sur les fenêtres évaluées :")
        print("     p10=%.2f  médiane=%.2f  p90=%.2f  max=%.2f  (seuil actuel %.2f)"
              % (np.percentile(d, 10), np.median(d), np.percentile(d, 90), d.max(),
                 SEUIL_DISSONANCE_DISTANCE))

    par_emotion = defaultdict(lambda: [0, 0])
    for r in ev:
        par_emotion[r["emotion"]][0] += 1
        if r["niveau"] != "NONE":
            par_emotion[r["emotion"]][1] += 1
    if par_emotion:
        print()
        print("  détail par émotion :")
        for emo, (n, a) in sorted(par_emotion.items(), key=lambda x: -x[1][1]):
            print("     %-22s %3d fenêtres, %3d alerte(s) (%.0f %%)"
                  % (emo, n, a, 100 * a / max(n, 1)))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corpus", required=True, help="dossier des .mp4 RAVDESS")
    p.add_argument("--mode", choices=("congruence", "croise"), default="congruence")
    p.add_argument("--limit", type=int, default=None, help="nombre de clips ou de paires")
    p.add_argument("--degrade", action="store_true",
                   help="ajoute une compression JPEG pour approcher un flux de visio")
    p.add_argument("--seed", type=int, default=0, help="graine du tirage des paires")
    p.add_argument("--window", type=float, default=None,
                   help="durée de la fenêtre d'analyse (défaut : celle du .env)")
    p.add_argument("--hop", type=float, default=None,
                   help="pas entre deux fenêtres (défaut : moitié de la fenêtre)")
    p.add_argument("--no-warmup", action="store_true",
                   help="n'ignore pas la première fenêtre de chaque clip")
    p.add_argument("--no-align-speech", action="store_true",
                   help="ne recale PAS les fenêtres sur le segment parlé. C'est le "
                        "comportement réel du dispositif, qui ignore où se trouve la "
                        "parole et analyse ce qui se présente.")
    p.add_argument("--live", action="store_true",
                   help="mode fidèle : reproduit exactement la boucle d'api.main. "
                        "Fenêtres de ANALYSIS_WINDOW_SECONDS qui se suivent sans "
                        "recouvrement, à partir du début du clip, sans recalage sur la "
                        "parole, fenêtre de reprise active, aucune dégradation ajoutée. "
                        "Écrase --window, --hop, --degrade, --no-warmup et "
                        "--no-align-speech.")
    p.add_argument("--csv", default=None, help="fichier CSV de sortie (une ligne par fenêtre)")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if args.live:
        # Le mode fidèle ne se négocie pas : toute option contraire est ignorée,
        # sans quoi un banc « live » avec un réglage d'évaluation resté actif
        # produirait des chiffres impossibles à interpréter.
        args.window = ANALYSIS_WINDOW_SECONDS
        args.hop = ANALYSIS_WINDOW_SECONDS
        args.degrade = False
        args.no_warmup = False
        args.no_align_speech = True

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="    %(levelname)s %(name)s : %(message)s", stream=sys.stdout,
    )

    clips, silent = find_clips(args.corpus)
    print("Corpus : %s" % os.path.abspath(args.corpus))
    print("  %d clip(s) audio+vidéo exploitables" % len(clips))
    if silent:
        print("  %d clip(s) « vidéo seule » (modalité 02) ignorés : leur piste audio "
              "est vide, aucune fenêtre ne serait exploitable" % len(silent))
    if not clips:
        print("Aucun clip exploitable.")
        return 1

    window = args.window or ANALYSIS_WINDOW_SECONDS
    hop = args.hop or (window / 2.0)
    warmup = 0 if args.no_warmup else None

    align_speech = not args.no_align_speech

    print()
    if args.live:
        print("MODE FIDÈLE : reproduction de la boucle d'api.main, sans aménagement.")
        print("  fenêtres de %.1f s qui se suivent sans recouvrement, à partir de t=0"
              % window)
        print("  aucun recalage sur la parole : le dispositif ignore où elle se trouve")
        print("  fenêtre de reprise active, aucune dégradation ajoutée à l'image")
        print("  sous-fenêtre vocale minimale : %.1f s (valeur de production)"
              % VOICE_SUBWINDOW_MIN_SECONDS)
        if VOICE_SUBWINDOW_MIN_SECONDS * 2 > window:
            print("  ATTENTION : deux sous-fenêtres vocales n'entrent pas dans %.1f s."
                  % window)
            print("  La fiabilité par concordance sera impossible et le service")
            print("  retombera sur le mode « intensité ».")
        print()
    print("Configuration : fenêtre %.1f s | pas %.1f s | image toutes les %.2f s | "
          "capture %d px%s%s%s"
          % (window, hop, FACE_SAMPLE_INTERVAL, CAPTURE_MAX_SIZE,
             " | dégradation JPEG" if args.degrade else "",
             " | sans fenêtre de reprise" if args.no_warmup else "",
             " | recalé sur la parole" if align_speech else " | sans recalage"))
    if window > 3.5:
        print("  Attention : les extraits RAVDESS durent environ 4 s. Une fenêtre de "
              "%.1f s ne laisse presque aucun point de mesure." % window)
    print()

    if args.mode == "congruence":
        rows = run_congruence(clips, args.degrade, args.limit, window, hop, warmup,
                              align_speech)
    else:
        rows = run_croise(clips, args.degrade, args.limit, args.seed, window, hop, warmup,
                          align_speech)

    summarise(rows, args.mode)

    if args.csv and rows:
        cols = ["fichier", "emotion", "intensite", "attendu", "fenetre", "debut_s", "evaluee",
                "ecartee", "images_visage", "dispersion", "visage", "fiab_visage",
                "voix", "fiab_voix", "sous_fenetres_voix", "distance", "niveau",
                "score", "vibration"]
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print()
        print("  %d ligne(s) écrites dans %s" % (len(rows), args.csv))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
