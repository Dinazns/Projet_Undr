# Frontend — Undr

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
- **Paramètres** : choix du périphérique audio (loopback) avec test de niveau,
  calibration des vibrations.

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
│   ├── hooks/              # useWebSocket, useElectron, useAudioDevices
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
