# Frontend | Undr

Application desktop Electron + React (Vite) pour l'assistant Undr. Elle affiche
un HUD transparent par-dessus la visioconférence et un tableau de bord d'analyse
post-séance, et communique en temps réel avec le backend.

## Fonctionnalités

- **HUD** : fenêtre translucide servant de mire, superposée à la zone vidéo du
  patient. C'est la zone que le backend capture et analyse.
- **Dashboard** : timeline des dissonances, mapping de Russell, graphiques de
  valence et de dissonance, notes cliniques.
- **WebSocket** : liaison temps réel avec le backend (envoi des coordonnées du
  HUD, réception des événements de dissonance).
- **Montre connectée** : test de la vibration et suivi de l'état BLE depuis les
  paramètres.
- **Paramètres** : langue de l'interface, choix du périphérique audio (loopback)
  avec test de niveau, réinitialisation du contexte d'analyse entre deux
  séquences, test des deux niveaux de vibration.
- **Bilingue** : français et anglais, y compris les libellés d'émotions et les
  légendes des graphiques. Le choix est conservé dans `localStorage` et propagé
  aux deux fenêtres, le HUD et le tableau de bord.

## Stack

- React 19 + React Router 7
- Electron 42 (portage desktop)
- Vite 8 (dev / build)
- Chart.js 4 + plugin zoom (graphiques du dashboard)

## Installation

```bash
cd Projet/front
npm install
```

## Utilisation

```bash
npm run dev      # serveur Vite + Electron avec HMR
npm run build    # build de production
npm run dist     # build + packaging Windows (NSIS + portable) dans release/
```

## Structure

```
front/
├── electron/               # Processus principal + preload
├── src/
│   ├── components/         # DissonanceChart, ValenceChart, RussellChart,
│   │                       # MiniWidget, Led, SettingsModal
│   ├── hooks/              # useWebSocket, useElectron, useAudioDevices,
│   │                       # useWindowDrag
│   ├── lib/                # constants, i18n, store (localStorage)
│   ├── pages/              # Hud, Dashboard
│   ├── styles/
│   ├── App.jsx
│   └── main.jsx
├── index.html
├── package.json
└── vite.config.js
```

## Communication avec le backend

WebSocket sur `ws://127.0.0.1:8000/ws`, messages au format JSON. Exemple d'un
événement de dissonance reçu :

```json
{
  "type": "dissonance",
  "timestamp": "14:22:07",
  "value": 75.5,
  "alert_level": "MODERATE",
  "face": "happy (80%)",
  "voice": "sad (70%)",
  "quadrant_face": "Q1 (Actif/Positif)",
  "quadrant_voice": "Q3 (Passif/Négatif)",
  "face_coords": [0.72, 0.63],
  "voice_coords": [-0.55, -0.34],
  "emotion_distance": 1.46
}
```

Les coordonnées `face_coords` / `voice_coords` (valence, arousal) alimentent le
mapping de Russell du dashboard.

Le backend envoie par ailleurs un message de télémétrie à **chaque** fenêtre,
qu'une dissonance ait été détectée ou non. Sans lui, l'interface resterait muette
tant qu'aucune alerte ne se déclenche, et un système qui fonctionne correctement
sans rien trouver serait indiscernable d'un système en panne. Ces événements ne
sont pas enregistrés, ils alimentent seulement la jauge du widget.

```json
{
  "type": "telemetry",
  "timestamp": "14:21:58",
  "face": "happy",
  "face_score": 78.4,
  "voice": "neutral",
  "voice_score": 61.2,
  "distance": 0.412,
  "alert_level": "NONE",
  "face_samples": 8,
  "face_dispersion": 0.121,
  "skipped": null,
  "window_seconds": 3.44
}
```

Le champ `skipped` porte le motif de rejet quand la fenêtre n'a pas été évaluée :
`visage`, `visage instable`, `voix` ou `reprise`.

Messages envoyés au backend : les coordonnées du HUD `{x, y, w, h}` à intervalle
régulier, `{"type": "test_vibration"}` et `{"type": "reset_context"}`.
