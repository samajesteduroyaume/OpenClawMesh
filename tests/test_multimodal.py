import asyncio

import pytest

from openclaw_mesh.engines.multimodal import MultiModalEngine


def test_multimodal_vision():
    engine = MultiModalEngine()

    async def _run():
        with pytest.raises(NotImplementedError, match="backend VLM"):
            await engine.analyze_image("not-a-real-image", prompt="Describe this UI component")

    asyncio.run(_run())


def test_multimodal_stt_and_tts():
    engine = MultiModalEngine()

    async def _run():
        with pytest.raises(NotImplementedError, match="backend STT"):
            await engine.transcribe_audio(audio_base64="mock_audio_data", language="fr")
        with pytest.raises(NotImplementedError, match="backend TTS"):
            await engine.synthesize_speech(text="Bonjour monde")

    asyncio.run(_run())
