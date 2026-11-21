"""Local, optional faster-whisper STT. Never invent transcript on model failure.

No network download by default. The operator explicitly installs the engine and model.
"""
import os
from pathlib import Path
from fastapi import HTTPException


class SpeechUnavailable(RuntimeError):
    pass


def transcribe_m4a(path: Path) -> tuple[str, int, str]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SpeechUnavailable("Instala faster-whisper en el backend") from exc
    name = os.environ.get("NEXO_WHISPER_MODEL", "base")
    root = Path(os.environ.get("NEXO_WHISPER_CACHE", str(Path.home() / ".cache" / "nexo-whisper")))
    allow_download = os.environ.get("NEXO_WHISPER_ALLOW_DOWNLOAD", "0") == "1"
    try:
        engine = WhisperModel(name, device="cpu", compute_type="int8",
                              download_root=str(root), local_files_only=not allow_download)
        segments, info = engine.transcribe(str(path), language="es", beam_size=3,
                                           vad_filter=True, condition_on_previous_text=False)
        duration = float(info.duration or 0)
        if duration > 60.5:
            raise ValueError("El audio supera 60 segundos")
        chunks=[]
        for segment in segments:
            chunks.append(segment.text.strip())
            if sum(len(x) for x in chunks) > 5000:
                raise ValueError("La transcripcion supera 5000 caracteres")
        text=" ".join(x for x in chunks if x).strip()
        if not text:
            raise ValueError("No se reconocio habla; revisa el audio")
        return text, int(duration * 1000), "faster-whisper:" + name
    except ValueError:
        raise
    except Exception as exc:
        # No internal paths, prompts, tokens or audio content in API error.
        raise SpeechUnavailable("Motor local no disponible o archivo de audio ilegible") from exc
