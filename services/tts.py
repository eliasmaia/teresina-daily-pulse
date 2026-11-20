import asyncio
import os
import edge_tts

DEFAULT_VOICE = "pt-BR-AntonioNeural"


async def _synthesize(text: str, output_path: str, voice: str, rate: str) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(output_path)


def generate_audio_mp3(
    script: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "+4%",
) -> str:
    """Sintetiza o roteiro em arquivo MP3 e retorna o caminho do arquivo gerado."""
    cleaned_script = " ".join(script.split())
    if not cleaned_script:
        raise ValueError("O roteiro de áudio está vazio; síntese cancelada.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    asyncio.run(_synthesize(cleaned_script, output_path, voice, rate))
    return output_path