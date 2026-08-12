import { useCallback, useEffect, useState } from 'react'
import { LANG_KEY } from './constants'

/**
 * Traduction de l'interface, français et anglais.
 *
 * La langue est conservée dans localStorage, que le HUD et le tableau de bord
 * partagent puisqu'ils tournent dans deux fenêtres du même Electron. Changer de
 * langue dans les paramètres du HUD met donc aussi le tableau de bord à jour,
 * via deux canaux : l'événement `storage` pour les autres fenêtres, et un
 * événement maison pour la fenêtre courante, que `storage` ne notifie pas.
 */

export const LANGS = [
  { code: 'fr', label: 'Français' },
  { code: 'en', label: 'English' },
]

export const DEFAULT_LANG = 'fr'
const LANG_EVENT = 'undr-lang-change'

const UI = {
  fr: {
    // Écran de consentement
    consentTitle: 'Consentement du patient',
    consentBody:
      "L'assistant analysera en local les expressions faciales et la voix du " +
      'patient dans ce cadre. Aucune image et aucun son ne sont enregistrés ni ' +
      'transmis : seuls des indicateurs émotionnels horodatés sont conservés, le ' +
      'temps de la séance.',
    consentAttest:
      "En démarrant, vous attestez avoir informé le patient et recueilli son " +
      "accord. L'horodatage de cette attestation figurera sur le compte-rendu de " +
      'séance.',
    start: "Démarrer l'assistance",
    starting: 'Démarrage...',
    backendOffline:
      "Le moteur d'analyse n'est pas connecté. Veuillez démarrer le backend.",
    dragWindow: 'Glisser pour déplacer la fenêtre',

    // Widget
    move: 'Déplacer',
    ledSensor: 'Capteur',
    gaugeTitle: 'Écart mesuré entre le visage et la voix',
    waiting: 'en attente…',
    connectWatch: 'Connecter la montre',
    disconnectWatch: 'Déconnecter la montre',
    settings: 'Paramètres',
    stop: 'Arrêter',

    // Fenêtres écartées (motifs renvoyés par le moteur)
    skipped_visage: 'visage absent',
    'skipped_visage instable': 'visage instable',
    skipped_voix: 'voix inexploitable',
    skipped_reprise: 'reprise en cours',

    // Paramètres
    language: 'Langue',
    languageHint: "Change la langue de l'interface, HUD et tableau de bord compris.",
    audioSection: 'Capture audio (voix)',
    audioHint:
      'Choisissez la sortie audio à intercepter (loopback). Testez le niveau ' +
      'pour vérifier que le son est bien capté.',
    device: 'Périphérique',
    defaultSpeaker: 'Haut-parleur par défaut',
    testSound: 'Tester le son',
    measuring: 'Mesure…',
    captureError: 'Erreur de capture sur ce périphérique',
    soundDetected: 'Son détecté ✓ (niveau {level}%)',
    noSound: 'Aucun son capté, lisez un son puis retestez',
    saveChoice: 'Enregistrer le choix',
    saving: 'Enregistrement…',
    saved: 'Enregistré ✓',
    contextSection: "Contexte d'analyse",
    contextHint:
      'Vide la mémoire des deux canaux. À utiliser en cas de changement de scène ' +
      "(fin d'appel, nouvelle séquence) : sans cela, le premier visage détecté " +
      'est comparé à la voix analysée juste avant.',
    resetContext: 'Réinitialiser le contexte',
    contextReset: 'Contexte réinitialisé ✓',
    braceletSection: 'Test du bracelet',
    testSevere: 'Tester alerte sévère',
    testVigilance: 'Tester vigilance',
    close: 'Fermer',

    // Erreurs des appels au backend
    audioApiUnavailable: 'API audio non disponible (backend éteint ?)',
    audioListError: 'Erreur de liste audio',
    audioTestUnavailable: 'API test audio non disponible',
    audioSelectUnavailable: 'API choix audio non disponible',

    // Tableau de bord
    dashboardTitle: 'Bilan de téléconsultation',
    closeApp: "Fermer l'application",
    timelineTitle: 'Timeline des dissonances émotionnelles',
    alertCount: '{n} alerte(s)',
    noData: 'Aucune donnée enregistrée pendant cette séance.',
    valenceTitle: 'Valence émotionnelle (voix + visage)',
    russellTitle: 'Mapping de Russell (visage ↔ voix)',
    russellHint:
      'Cliquez sur un pic de la timeline pour afficher les coordonnées exactes ' +
      "(valence / arousal) du visage et de la voix à cet instant T.",
    notesTitle: 'Notes cliniques',
    notesPlaceholder: 'Saisissez vos observations post-séance ici...',
    savePdf: 'Enregistrer le compte-rendu PDF',
    savedShort: 'Enregistré',
    saveError: "Erreur d'enregistrement",

    // Graphiques
    dissonanceLevel: 'Niveau de dissonance',
    dissonanceTooltip: 'Dissonance : {v}%',
    faceTooltip: 'Visage : {v}',
    voiceTooltip: 'Voix : {v}',
    // Le français met une espace avant les deux-points, l'anglais non.
    labelSep: ' : ',
    face: 'Visage',
    voice: 'Voix',
    incongruence: 'Incongruence (visage ↔ voix)',
    positive: 'Positif (voix + visage)',
    negative: 'Négatif (voix + visage)',
    neutral: 'Neutre (voix + visage)',
    axisValence: 'Valence (− négatif → + positif)',
    axisArousal: 'Arousal (− calme → + actif)',
  },

  en: {
    consentTitle: 'Patient consent',
    consentBody:
      'The assistant will analyse the facial expressions and the voice of the ' +
      'patient inside this frame, locally. No image and no sound is recorded or ' +
      'transmitted: only timestamped emotional indicators are kept, for the ' +
      'duration of the session.',
    consentAttest:
      'By starting, you certify that you have informed the patient and obtained ' +
      'their agreement. The timestamp of this attestation will appear on the ' +
      'session report.',
    start: 'Start assistance',
    starting: 'Starting...',
    backendOffline: 'The analysis engine is not connected. Please start the backend.',
    dragWindow: 'Drag to move the window',

    move: 'Move',
    ledSensor: 'Sensor',
    gaugeTitle: 'Measured gap between face and voice',
    waiting: 'waiting…',
    connectWatch: 'Connect the watch',
    disconnectWatch: 'Disconnect the watch',
    settings: 'Settings',
    stop: 'Stop',

    skipped_visage: 'no face',
    'skipped_visage instable': 'unstable face',
    skipped_voix: 'unusable voice',
    skipped_reprise: 'warming up',

    language: 'Language',
    languageHint: 'Changes the interface language, both HUD and dashboard.',
    audioSection: 'Audio capture (voice)',
    audioHint:
      'Choose the audio output to intercept (loopback). Test the level to check ' +
      'that sound is properly captured.',
    device: 'Device',
    defaultSpeaker: 'Default speaker',
    testSound: 'Test sound',
    measuring: 'Measuring…',
    captureError: 'Capture error on this device',
    soundDetected: 'Sound detected ✓ (level {level}%)',
    noSound: 'No sound captured, play something then test again',
    saveChoice: 'Save this choice',
    saving: 'Saving…',
    saved: 'Saved ✓',
    contextSection: 'Analysis context',
    contextHint:
      'Clears the memory of both channels. Use it when the scene changes (end of ' +
      'a call, new sequence): without it, the first face detected is compared to ' +
      'the voice analysed just before.',
    resetContext: 'Reset the context',
    contextReset: 'Context reset ✓',
    braceletSection: 'Wristband test',
    testSevere: 'Test severe alert',
    testVigilance: 'Test vigilance',
    close: 'Close',

    audioApiUnavailable: 'Audio API unavailable (backend down?)',
    audioListError: 'Could not list audio devices',
    audioTestUnavailable: 'Audio test API unavailable',
    audioSelectUnavailable: 'Audio selection API unavailable',

    dashboardTitle: 'Teleconsultation summary',
    closeApp: 'Close the application',
    timelineTitle: 'Emotional dissonance timeline',
    alertCount: '{n} alert(s)',
    noData: 'No data recorded during this session.',
    valenceTitle: 'Emotional valence (voice + face)',
    russellTitle: 'Russell mapping (face ↔ voice)',
    russellHint:
      'Click a peak on the timeline to display the exact coordinates (valence / ' +
      'arousal) of the face and the voice at that moment.',
    notesTitle: 'Clinical notes',
    notesPlaceholder: 'Type your post-session observations here...',
    savePdf: 'Save the PDF report',
    savedShort: 'Saved',
    saveError: 'Could not save',

    dissonanceLevel: 'Dissonance level',
    dissonanceTooltip: 'Dissonance: {v}%',
    faceTooltip: 'Face: {v}',
    voiceTooltip: 'Voice: {v}',
    labelSep: ': ',
    face: 'Face',
    voice: 'Voice',
    incongruence: 'Incongruence (face ↔ voice)',
    positive: 'Positive (voice + face)',
    negative: 'Negative (voice + face)',
    neutral: 'Neutral (voice + face)',
    axisValence: 'Valence (− negative → + positive)',
    axisArousal: 'Arousal (− calm → + active)',
  },
}

/**
 * Étiquettes que le moteur produit réellement. Le modèle facial est entraîné
 * sur AffectNet, le modèle vocal sur MSP-Podcast, et les deux sont projetés
 * dans le plan de Russell. Ces vingt clés couvrent l'intégralité des sorties
 * possibles, elles reprennent EMOTION_COORDINATES côté backend.
 */
const EMOTION_LABELS = {
  fr: {
    happy: 'Joie',
    joy: 'Joie',
    surprise: 'Surprise',
    excited: 'Excitation',
    enthusiastic: 'Enthousiasme',
    calm: 'Calme',
    content: 'Contentement',
    satisfied: 'Satisfaction',
    relaxed: 'Détente',
    sad: 'Tristesse',
    bored: 'Ennui',
    tired: 'Fatigue',
    disappointed: 'Déception',
    confused: 'Confusion',
    angry: 'Colère',
    fear: 'Peur',
    disgust: 'Dégoût',
    anxious: 'Anxiété',
    frustrated: 'Frustration',
    neutral: 'Neutre',
  },
  en: {
    happy: 'Happiness',
    joy: 'Joy',
    surprise: 'Surprise',
    excited: 'Excitement',
    enthusiastic: 'Enthusiasm',
    calm: 'Calm',
    content: 'Contentment',
    satisfied: 'Satisfaction',
    relaxed: 'Relaxed',
    sad: 'Sadness',
    bored: 'Boredom',
    tired: 'Tiredness',
    disappointed: 'Disappointment',
    confused: 'Confusion',
    angry: 'Anger',
    fear: 'Fear',
    disgust: 'Disgust',
    anxious: 'Anxiety',
    frustrated: 'Frustration',
    neutral: 'Neutral',
  },
}

function readLang() {
  try {
    const stored = localStorage.getItem(LANG_KEY)
    return UI[stored] ? stored : DEFAULT_LANG
  } catch {
    return DEFAULT_LANG
  }
}

let currentLang = readLang()

export function getLang() {
  return currentLang
}

export function setLang(lang) {
  if (!UI[lang] || lang === currentLang) return
  currentLang = lang
  try {
    localStorage.setItem(LANG_KEY, lang)
  } catch {
    // Mode privé ou quota plein : la langue reste valable pour cette fenêtre.
  }
  window.dispatchEvent(new CustomEvent(LANG_EVENT, { detail: lang }))
}

/**
 * Traduit une clé, en remplaçant les {variables} éventuelles. Utilisable hors
 * de React, où l'on n'a pas accès au hook.
 */
export function t(key, vars, lang = currentLang) {
  const dict = UI[lang] || UI[DEFAULT_LANG]
  let text = dict[key] ?? UI[DEFAULT_LANG][key] ?? key
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.replaceAll(`{${name}}`, String(value))
    }
  }
  return text
}

/**
 * Traduit une étiquette d'émotion renvoyée par le moteur, du type « happy (85%) ».
 * Le pourcentage est conservé tel quel.
 */
export function translateEmotion(emotionString, lang = currentLang) {
  if (!emotionString || typeof emotionString !== 'string') return emotionString

  const match = emotionString.match(/^(.+?)( \(\d+%\))?$/)
  if (!match) return emotionString

  const name = match[1].trim().toLowerCase()
  const percentage = match[2] || ''
  const dict = EMOTION_LABELS[lang] || EMOTION_LABELS[DEFAULT_LANG]

  return dict[name] ? dict[name] + percentage : emotionString
}

/** Traduit le motif de rejet d'une fenêtre, renvoyé en français par le moteur. */
export function translateSkipped(reason, lang = currentLang) {
  if (!reason) return reason
  return t(`skipped_${reason}`, null, lang)
}

/**
 * Abonne un composant à la langue courante. Le changement est propagé dans la
 * fenêtre courante par l'événement maison, et dans les autres fenêtres par
 * l'événement `storage` du navigateur.
 */
export function useI18n() {
  const [lang, setLangState] = useState(currentLang)

  useEffect(() => {
    const onLocal = (e) => setLangState(e.detail)
    const onStorage = (e) => {
      if (e.key === LANG_KEY) {
        currentLang = readLang()
        setLangState(currentLang)
      }
    }
    window.addEventListener(LANG_EVENT, onLocal)
    window.addEventListener('storage', onStorage)
    return () => {
      window.removeEventListener(LANG_EVENT, onLocal)
      window.removeEventListener('storage', onStorage)
    }
  }, [])

  const translate = useCallback((key, vars) => t(key, vars, lang), [lang])

  return { lang, setLang, t: translate }
}
