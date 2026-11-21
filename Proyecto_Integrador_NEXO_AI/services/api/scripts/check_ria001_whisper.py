"""Verify real on-device Whisper decoding on a user-provided M4A; no upload.

Usage: python -m scripts.check_ria001_whisper C:\\path\\to\\audio.m4a
"""
import sys
from pathlib import Path
from app.modules.ai.speech import transcribe_m4a

def main():
    if len(sys.argv)!=2:
        raise SystemExit('Uso: python -m scripts.check_ria001_whisper RUTA_DEL_AUDIO_M4A')
    p=Path(sys.argv[1]).expanduser().resolve()
    if not p.is_file() or p.suffix.lower()!='.m4a':
        raise SystemExit('Selecciona un audio M4A local existente')
    text,duration,engine=transcribe_m4a(p)
    print('RIA-001 WHISPER REAL OK')
    print('Motor:',engine,'| Segundos:',round(duration/1000,2))
    print('Texto sin revisar:',text[:5000])

if __name__=='__main__':main()
