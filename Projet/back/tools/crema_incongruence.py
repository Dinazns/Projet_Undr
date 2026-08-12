"""
Extraction des clips CREMA-D perçus différemment selon le canal.

CREMA-D (Cao et al., 2014) a fait noter chacun de ses 7 442 clips par des
humains dans TROIS conditions séparées : voix seule, visage seul, audiovisuel.
Le fichier `processedResults/summaryTable.csv` livre donc, pour chaque clip, un
`VoiceVote` et un `FaceVote` indépendants.

Les clips où `FaceVote != VoiceVote` sont ceux où des annotateurs humains ont
perçu une émotion dans la voix et une autre sur le visage. C'est une
incongruence inter-canaux **attestée par jugement humain**, sur du matériel
libre, et non une dissonance fabriquée par montage.

Ce script produit deux listes de fichiers, à passer ensuite au banc
d'évaluation : la liste concordante mesure les faux positifs, la liste
discordante mesure les détections.

    python -m tools.crema_incongruence --summary summaryTable.csv --out .

Limites : les clips restent des phrases jouées de deux à trois secondes, et le
désaccord des annotateurs peut refléter l'ambiguïté du jeu d'acteur autant
qu'un masquage authentique. À déclarer.
"""
import argparse
import csv
import os
from collections import Counter, defaultdict

# Correspondance des libellés de réponse vers les codes à une lettre.
REPONSE_VERS_CODE = {
    "A": "A", "D": "D", "F": "F", "H": "H", "N": "N", "S": "S",
    "ANG": "A", "DIS": "D", "FEA": "F", "HAP": "H", "NEU": "N", "SAD": "S",
    "ANGER": "A", "DISGUST": "D", "FEAR": "F", "HAPPY": "H",
    "NEUTRAL": "N", "SAD ": "S", "SADNESS": "S",
}

# queryType dans finishedResponses.csv : 1 = voix seule, 2 = visage seul,
# 3 = audiovisuel.
QUERY_VOIX, QUERY_VISAGE = "1", "2"

EMO = {"A": "colère", "D": "dégoût", "F": "peur",
       "H": "joie", "N": "neutre", "S": "tristesse"}


def read_summary(path):
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("FileName")]


def _code(valeur):
    if not valeur:
        return None
    v = str(valeur).strip().strip('"').upper()
    if "_" in v:                      # format "H_50"
        v = v.split("_")[0]
    return REPONSE_VERS_CODE.get(v)


def build_summary_from_responses(path):
    """
    Reconstruit VoiceVote et FaceVote à partir des réponses brutes.

    summaryTable.csv est un fichier dérivé, absent de certains miroirs. Les
    réponses individuelles, elles, sont toujours présentes : chaque annotateur y
    a jugé un clip dans UNE condition (voix seule, visage seul ou audiovisuel).
    Le vote majoritaire par clip et par condition redonne exactement les deux
    colonnes dont on a besoin, sans dépendre d'aucun téléchargement.
    """
    votes = defaultdict(lambda: {QUERY_VOIX: Counter(), QUERY_VISAGE: Counter()})
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            clip = (r.get("clipName") or "").strip().strip('"')
            qt = (r.get("queryType") or "").strip().strip('"')
            code = _code(r.get("respEmo"))
            if not clip or qt not in (QUERY_VOIX, QUERY_VISAGE) or not code:
                continue
            votes[clip][qt][code] += 1

    lignes = []
    for clip, par_condition in votes.items():
        voix, visage = par_condition[QUERY_VOIX], par_condition[QUERY_VISAGE]
        if not voix or not visage:
            continue

        def majoritaire(compteur):
            n = max(compteur.values())
            gagnants = sorted(k for k, v in compteur.items() if v == n)
            return ":".join(gagnants)      # ex-aequo notés comme dans le fichier officiel

        lignes.append({
            "FileName": os.path.splitext(clip)[0],
            "VoiceVote": majoritaire(voix),
            "FaceVote": majoritaire(visage),
        })
    return lignes


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--summary", default=None,
                   help="chemin de processedResults/summaryTable.csv")
    p.add_argument("--responses", default=None,
                   help="chemin de finishedResponses.csv : reconstruit les votes "
                        "par condition si summaryTable.csv est absent du miroir")
    p.add_argument("--out", default=".", help="dossier de sortie des listes")
    p.add_argument("--strict", action="store_true",
                   help="écarte les votes ambigus (plusieurs émotions séparées par ':')")
    p.add_argument("--balance", action="store_true", default=True,
                   help="égalise les deux classes dans le fichier d'étiquettes")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    if not args.summary and not args.responses:
        p.error("indiquez --summary ou --responses")
    if args.summary and os.path.exists(args.summary):
        rows = read_summary(args.summary)
        print("Source : %s" % os.path.abspath(args.summary))
    elif args.responses:
        rows = build_summary_from_responses(args.responses)
        print("Source : %s (votes reconstruits par condition)"
              % os.path.abspath(args.responses))
    else:
        p.error("fichier introuvable : %s" % args.summary)
    concordants, discordants, ambigus = [], [], []

    croisement = defaultdict(int)
    for r in rows:
        face, voice = r["FaceVote"].strip(), r["VoiceVote"].strip()
        if ":" in face or ":" in voice:
            ambigus.append(r["FileName"])
            if args.strict:
                continue
            face, voice = face.split(":")[0], voice.split(":")[0]
        (concordants if face == voice else discordants).append(r["FileName"])
        croisement[(EMO.get(face, face), EMO.get(voice, voice))] += 1

    total = len(concordants) + len(discordants)
    print("Clips analysés            : %d" % len(rows))
    print("  votes ambigus            : %d" % len(ambigus))
    print("  visage == voix           : %d (%.1f %%)" % (len(concordants), 100 * len(concordants) / max(total, 1)))
    print("  visage != voix           : %d (%.1f %%)  <- incongruence perçue" % (len(discordants), 100 * len(discordants) / max(total, 1)))

    print()
    print("Croisements les plus fréquents (visage perçu -> voix perçue) :")
    disc = [(k, v) for k, v in croisement.items() if k[0] != k[1]]
    for (f, v), n in sorted(disc, key=lambda x: -x[1])[:12]:
        print("   visage %-10s / voix %-10s : %4d clips" % (f, v, n))

    os.makedirs(args.out, exist_ok=True)
    for name, items in (("crema_congruents.txt", concordants),
                        ("crema_discordants.txt", discordants)):
        path = os.path.join(args.out, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(items) + "\n")
        print()
        print("  %d nom(s) écrits dans %s" % (len(items), path))

    # Fichier d'étiquettes directement exploitable par tools.benchmark.
    import random
    pos, neg = list(discordants), list(concordants)
    if args.balance:
        rnd = random.Random(args.seed)
        rnd.shuffle(pos)
        rnd.shuffle(neg)
        n = min(len(pos), len(neg))
        pos, neg = pos[:n], neg[:n]
    labels_path = os.path.join(args.out, "crema_labels.csv")
    with open(labels_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clip", "label"])
        for c in pos:
            w.writerow([c, 1])
        for c in neg:
            w.writerow([c, 0])
    print()
    print("  %d ligne(s) écrites dans %s (%d dissonants, %d congruents)"
          % (len(pos) + len(neg), labels_path, len(pos), len(neg)))
    print()
    print("  Suite :")
    print("     python -m tools.benchmark --labels %s --media <racine CREMA-D>" % labels_path)


if __name__ == "__main__":
    raise SystemExit(main())
