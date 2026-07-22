
# Undr Assistant - Frontend

Frontend Electron + React + Vite pour le système d'assistance multimodale Undr Assistant.

## Fonctionnalités

- **HUD (Heads-Up Display)** : Capture de l'écran pour analyser les expressions faciales
- **Dashboard** : Visualisation des données de dissonance émotionnelle (graphiques, historique)
- **WebSocket** : Communication en temps réel avec le backend
- **Montre connectée BLE** : Réception des vibrations lors de détection de dissonance
- **Paramètres** : Configuration de la zone de capture, tests de vibration, etc.

## Stack technique

### Dépendances principales
- **React 19.2.7** : Interface utilisateur
- **Electron 42.4.1** : Application desktop
- **Vite 8.0.12** : Build et développement rapide
- **React Router 7.18.0** : Gestion des routes (HUD / Dashboard)
- **Chart.js 4.5.1** : Visualisation des données avec graphiques
- **chartjs-plugin-zoom 2.2.0** : Zoom sur les graphiques

### Outils de développement
- **ESLint** : Linting du code
- **electron-builder 26.15.3** : Packaging de l'application
- **vite-plugin-electron** : Intégration Vite + Electron

## Installation et configuration

### 1. Prérequis
- Node.js 20+
- npm ou yarn

### 2. Installation des dépendances
```bash
cd front
npm install
```

## Utilisation

### Développement
```bash
npm run dev
```

Cette commande démarre :
1. Le serveur Vite pour le frontend React
2. L'application Electron avec HMR (Hot Module Replacement)

### Build pour la production
```bash
npm run build
```

### Build et packaging
```bash
npm run dist
```

Génère un package pour Windows (NSIS + portable) dans le dossier `release/`.

## Structure du projet

```
front/
├── electron/               # Fichiers Electron
│   ├── main.js            # Processus principal Electron
│   └── preload.js         # Script de préchargement
├── src/
│   ├── components/        # Composants React
│   │   ├── DissonanceChart.jsx
│   │   ├── Led.jsx
│   │   ├── MiniWidget.jsx
│   │   ├── SettingsModal.jsx
│   │   └── ValenceChart.jsx
│   ├── hooks/             # Hooks personnalisés
│   │   ├── useElectron.js
│   │   └── useWebSocket.js
│   ├── lib/               # Fonctionnalités utilitaires
│   │   ├── constants.js
│   │   ├── i18n.js        # Internationalisation
│   │   └── store.js       # État global (Zustand-like simple)
│   ├── pages/             # Pages de l'application
│   │   ├── Dashboard.jsx
│   │   └── Hud.jsx
│   ├── styles/            # Styles CSS
│   ├── App.jsx            # Composant principal
│   └── main.jsx           # Point d'entrée React
├── index.html
├── package.json
└── vite.config.js
```

## Communication avec le backend

Le frontend utilise un WebSocket pour communiquer avec le backend en temps réel :
- URL de connexion : `ws://127.0.0.1:8000/ws`
- Format de données : JSON

### Données reçues du backend
```json
{
  "type": "dissonance",
  "timestamp": "HH:MM:SS",
  "value": 75.5,
  "alert_level": "MODERATE",
  "face": "happy (80%)",
  "voice": "sad (70%)",
  "quadrant_face": "Q1 (Actif/Positif)",
  "quadrant_voice": "Q3 (Passif/Négatif)",
  "emotion_distance": 1.8
}
```

## Références scientifiques

Ce projet s'appuie sur les recherches de HumeAI :
- Modèle circumplex de Russell (1980) : Valence + Arousal
- Analyse multimodale (expression faciale + prosodie vocale)
- Détection de dissonance émotionnelle

Voir le dossier `hume-research-publications/` pour les publications complètes.

