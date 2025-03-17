import os
import json
import time
import wave
import pyaudio
import datetime
import threading
import logging
import difflib
import numpy as np
from queue import Queue
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import torch
from pathlib import Path
import io
import ffmpeg
import soundfile as sf
import librosa
import whisper

# Configuration des chemins et dossiers
BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = BASE_DIR / "models"
RECORDINGS_DIR = BASE_DIR / "recordings"
HISTORY_DIR = BASE_DIR / "history"

for directory in [MODELS_DIR, RECORDINGS_DIR, HISTORY_DIR]:
    directory.mkdir(exist_ok=True, parents=True)

# Configuration du logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(BASE_DIR / "voice_recognition.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AlfredVoiceRecognition")

# -----------------------------------------------------------------------------------
# Classe pour représenter une commande vocale
@dataclass
class VoiceCommand:
    text: str
    timestamp: float
    confidence: float
    audio_duration: float
    engine: str
    audio_path: Optional[str] = None
    processed: bool = False
    matched_command: Optional[str] = None
    execution_success: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "timestamp": self.timestamp,
            "datetime": datetime.datetime.fromtimestamp(self.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            "confidence": self.confidence,
            "audio_duration": self.audio_duration,
            "engine": self.engine,
            "audio_path": self.audio_path,
            "processed": self.processed,
            "matched_command": self.matched_command,
            "execution_success": self.execution_success
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VoiceCommand':
        return cls(
            text=data["text"],
            timestamp=data["timestamp"],
            confidence=data["confidence"],
            audio_duration=data["audio_duration"],
            engine=data["engine"],
            audio_path=data.get("audio_path"),
            processed=data.get("processed", False),
            matched_command=data.get("matched_command"),
            execution_success=data.get("execution_success")
        )

# -----------------------------------------------------------------------------------
# Classe abstraite pour les moteurs de reconnaissance vocale
class VoiceRecognitionEngine:
    def __init__(self, model_path: Optional[str] = None, language: str = "fr"):
        self.model_path = model_path
        self.language = language
        self.is_ready = False

    def initialize(self) -> bool:
        raise NotImplementedError("Méthode à implémenter dans les classes dérivées")

    def transcribe_audio(self, audio_path: str) -> Tuple[str, float]:
        raise NotImplementedError("Méthode à implémenter dans les classes dérivées")

    def transcribe_audio_data(self, audio_data: bytes) -> Tuple[str, float]:
        raise NotImplementedError("Méthode à implémenter dans les classes dérivées")

    @property
    def name(self) -> str:
        raise NotImplementedError("Méthode à implémenter dans les classes dérivées")

# -----------------------------------------------------------------------------------
# Moteur de reconnaissance vocale utilisant Whisper d'OpenAI (modifié pour la transcription en mémoire)
class WhisperEngine(VoiceRecognitionEngine):
    def __init__(self, model_name: str = "small", language: str = "fr", device: str = "auto", use_beam_search: bool = True):
        super().__init__(model_path=None, language=language)
        self.model_name = model_name
        self.device = device
        self.use_beam_search = use_beam_search
        self.model = None

    def initialize(self) -> bool:
        try:
            import whisper
            logger.info(f"Initialisation du moteur Whisper avec le modèle {self.model_name}")
            if self.device == "auto":
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = whisper.load_model(
                self.model_name,
                device=self.device,
                download_root=str(MODELS_DIR)
            )
            logger.info(f"Modèle Whisper {self.model_name} chargé sur {self.device}")
            self.is_ready = True
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de Whisper: {str(e)}")
            self.is_ready = False
            return False

    def transcribe_audio_data(self, audio_data: bytes) -> Tuple[str, float]:
        try:
            # Conversion en mémoire avec ffmpeg pour obtenir un fichier WAV
            process = (
                ffmpeg
                .input('pipe:0')
                .output('pipe:1', format='wav')
                .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True)
            )
            out, err = process.communicate(input=audio_data)
            if process.returncode != 0:
                logger.error(f"Erreur ffmpeg: {err.decode('utf-8')}")
                return "", 0.0
            audio_buffer = io.BytesIO(out)
            audio, sr = sf.read(audio_buffer)
            audio = np.array(audio, dtype=np.float32)
            if sr != self.model.dims.sample_rate:
                audio = librosa.resample(audio, orig_sr=sr, target_sr=self.model.dims.sample_rate)
            mel = whisper.log_mel_spectrogram(audio)
            options = whisper.DecodingOptions(
                language=self.language,
                beam_size=5 if self.use_beam_search else None,
                best_of=5 if self.use_beam_search else None
            )
            result = whisper.decode(self.model, mel, options)
            text = result.text.strip()
            confidence = 0.8  # Valeur par défaut (Whisper ne fournit pas directement un score de confiance)
            logger.debug(f"Transcription en mémoire réussie: '{text}' avec confiance {confidence:.2f}")
            return text, confidence
        except Exception as e:
            logger.error(f"Erreur lors de la transcription Whisper (audio_data): {str(e)}")
            return "", 0.0

    @property
    def name(self) -> str:
        return f"whisper_{self.model_name}"

# -----------------------------------------------------------------------------------
# Moteur de reconnaissance vocale utilisant Vosk (version inchangée)
class VoskEngine(VoiceRecognitionEngine):
    def __init__(self, model_path: Optional[str] = None, language: str = "fr"):
        model_directory = MODELS_DIR / f"vosk_{language}"
        if model_path is None:
            model_path = str(model_directory)
        super().__init__(model_path=model_path, language=language)
        self.model = None
        self.recognizer = None

    def initialize(self) -> bool:
        try:
            from vosk import Model, KaldiRecognizer
            if not os.path.exists(self.model_path) or not os.path.isdir(self.model_path):
                logger.info(f"Modèle Vosk non trouvé à {self.model_path}, téléchargement...")
                self._download_model()
            logger.info(f"Chargement du modèle Vosk depuis {self.model_path}")
            self.model = Model(self.model_path)
            self.recognizer = KaldiRecognizer(self.model, 16000)
            self.recognizer.SetWords(True)
            logger.info("Modèle Vosk chargé avec succès")
            self.is_ready = True
            return True
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de Vosk: {str(e)}")
            self.is_ready = False
            return False

    def _download_model(self):
        import urllib.request
        import zipfile
        os.makedirs(self.model_path, exist_ok=True)
        model_urls = {
            "fr": "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip",
            "en": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        }
        if self.language not in model_urls:
            raise ValueError(f"Pas de modèle Vosk disponible pour la langue {self.language}")
        model_url = model_urls[self.language]
        zip_path = f"{self.model_path}.zip"
        logger.info(f"Téléchargement du modèle Vosk depuis {model_url}")
        urllib.request.urlretrieve(model_url, zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(os.path.dirname(self.model_path))
        extracted_dir = zip_path.replace(".zip", "")
        if os.path.exists(extracted_dir) and extracted_dir != self.model_path:
            os.rename(extracted_dir, self.model_path)
        if os.path.exists(zip_path):
            os.remove(zip_path)

    def transcribe_audio(self, audio_path: str) -> Tuple[str, float]:
        if not self.is_ready or self.model is None:
            raise RuntimeError("Le moteur Vosk n'est pas initialisé")
        try:
            from vosk import KaldiRecognizer
            self.recognizer = KaldiRecognizer(self.model, 16000)
            self.recognizer.SetWords(True)
            with wave.open(audio_path, "rb") as wf:
                if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
                    logger.warning(f"Audio {audio_path} n'est pas au format attendu (mono, 16-bit)")
                results = []
                while True:
                    data = wf.readframes(4000)
                    if len(data) == 0:
                        break
                    if self.recognizer.AcceptWaveform(data):
                        results.append(json.loads(self.recognizer.Result()))
                final_result = json.loads(self.recognizer.FinalResult())
                results.append(final_result)
            transcribed_text = " ".join([result.get("text", "") for result in results]).strip()
            confidence = 0.0
            word_count = 0
            for result in results:
                if "result" in result:
                    for word in result["result"]:
                        confidence += word.get("conf", 0.0)
                        word_count += 1
            if word_count > 0:
                confidence = confidence / word_count
            else:
                confidence = 0.5
            logger.debug(f"Vosk a transcrit: '{transcribed_text}' avec une confiance de {confidence:.2f}")
            return transcribed_text, confidence
        except Exception as e:
            logger.error(f"Erreur lors de la transcription Vosk: {str(e)}")
            return "", 0.0

    def transcribe_audio_data(self, audio_data: bytes) -> Tuple[str, float]:
        if not self.is_ready or self.model is None:
            raise RuntimeError("Le moteur Vosk n'est pas initialisé")
        try:
            from vosk import KaldiRecognizer
            self.recognizer = KaldiRecognizer(self.model, 16000)
            self.recognizer.SetWords(True)
            self.recognizer.AcceptWaveform(audio_data)
            result = json.loads(self.recognizer.FinalResult())
            transcribed_text = result.get("text", "").strip()
            confidence = 0.0
            word_count = 0
            if "result" in result:
                for word in result["result"]:
                    confidence += word.get("conf", 0.0)
                    word_count += 1
            if word_count > 0:
                confidence = confidence / word_count
            else:
                confidence = 0.5
            logger.debug(f"Vosk a transcrit (audio_data): '{transcribed_text}' avec une confiance de {confidence:.2f}")
            return transcribed_text, confidence
        except Exception as e:
            logger.error(f"Erreur lors de la transcription Vosk (audio_data): {str(e)}")
            return "", 0.0

    @property
    def name(self) -> str:
        return f"vosk_{self.language}"

# -----------------------------------------------------------------------------------
# Classe pour enregistrer l'audio depuis le microphone avec calibration du seuil de bruit
class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1, chunk_size: int = 1024):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.pyaudio_instance = None
        self.stream = None
        self.is_recording = False
        self.frames = []
        self.record_thread = None
        self.silence_threshold = 500  # Valeur par défaut, sera recalibrée
        self.silence_duration = 1.0
        self.max_duration = 10.0

    def calibrate_noise(self, duration: float = 2.0) -> None:
        if self.pyaudio_instance is None:
            self.pyaudio_instance = pyaudio.PyAudio()
        stream = self.pyaudio_instance.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size
        )
        frames = []
        end_time = time.time() + duration
        while time.time() < end_time:
            try:
                data = stream.read(self.chunk_size, exception_on_overflow=False)
                frames.append(data)
            except Exception as e:
                logger.error(f"Erreur lors de la calibration du bruit: {str(e)}")
                break
        stream.stop_stream()
        stream.close()
        all_data = np.concatenate([np.frombuffer(frame, dtype=np.int16) for frame in frames])
        average_amplitude = np.mean(np.abs(all_data))
        self.silence_threshold = average_amplitude * 1.5
        logger.info(f"Seuil de silence calibré à : {self.silence_threshold:.2f}")

    def calculate_audio_duration(self) -> float:
        if not self.frames:
            return 0.0
        total_bytes = sum(len(frame) for frame in self.frames)
        sample_width = 2  # 16-bit = 2 octets
        total_samples = total_bytes / sample_width
        duration = total_samples / self.sample_rate
        return duration

    def start_recording(self, silence_detection: bool = True) -> None:
        if self.is_recording:
            logger.warning("L'enregistrement est déjà en cours")
            return
        if self.pyaudio_instance is None:
            self.pyaudio_instance = pyaudio.PyAudio()
        self.stream = self.pyaudio_instance.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size
        )
        self.frames = []
        self.is_recording = True
        self.record_thread = threading.Thread(target=self._record_thread_func, args=(silence_detection,))
        self.record_thread.daemon = True
        self.record_thread.start()
        logger.debug("Enregistrement audio démarré")

    def stop_recording(self) -> None:
        if not self.is_recording:
            logger.warning("Aucun enregistrement en cours")
            return
        self.is_recording = False
        if self.record_thread and self.record_thread.is_alive():
            self.record_thread.join(timeout=1.0)
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        logger.debug("Enregistrement audio arrêté")

    def _record_thread_func(self, silence_detection: bool) -> None:
        start_time = time.time()
        silence_start = None
        while self.is_recording:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                self.frames.append(data)
                current_duration = time.time() - start_time
                if current_duration >= self.max_duration:
                    logger.debug(f"Durée maximale atteinte ({self.max_duration}s)")
                    self.is_recording = False
                    break
                if silence_detection:
                    audio_data = np.frombuffer(data, dtype=np.int16)
                    volume_norm = np.abs(audio_data).mean()
                    if volume_norm < self.silence_threshold:
                        if silence_start is None:
                            silence_start = time.time()
                        elif time.time() - silence_start >= self.silence_duration:
                            logger.debug(f"Silence détecté pendant {self.silence_duration}s")
                            self.is_recording = False
                            break
                    else:
                        silence_start = None
            except Exception as e:
                logger.error(f"Erreur lors de l'enregistrement: {str(e)}")
                self.is_recording = False
                break

    def get_audio_data(self) -> bytes:
        if not self.frames:
            logger.warning("Pas de données audio enregistrées")
            return b""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(self.frames))
        return wav_buffer.getvalue()

    def save_audio(self, file_path: str) -> bool:
        if not self.frames:
            logger.warning("Pas de données audio à sauvegarder")
            return False
        try:
            with wave.open(file_path, "wb") as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(b''.join(self.frames))
            logger.debug(f"Audio sauvegardé dans {file_path}")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de l'audio: {str(e)}")
            return False

    def release(self) -> None:
        if self.is_recording:
            self.stop_recording()
        if self.pyaudio_instance:
            self.pyaudio_instance.terminate()
            self.pyaudio_instance = None
            logger.debug("Ressources PyAudio libérées")

# Fin du fichier voice-recognition-module.py
