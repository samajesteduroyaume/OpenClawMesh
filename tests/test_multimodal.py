import asyncio
import pytest
from openclaw_mesh.engines.multimodal import MultiModalEngine


def test_multimodal_vision():
    engine = MultiModalEngine()

    async def _run():
        res = await engine.analyze_image(
            image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            prompt="Describe this UI component",
        )
        assert "description" in res
        assert "detected_objects" in res
        assert res["duration_ms"] >= 0

    asyncio.run(_run())


def test_multimodal_stt_and_tts():
    engine = MultiModalEngine()

    async def _run():
        # 1. Test Speech-to-Text Whisper
        stt_res = await engine.transcribe_audio(audio_base64="mock_audio_data", language="fr")
        assert "transcription" in stt_res
        assert stt_res["confidence"] > 0.9

        # 2. Test Text-to-Speech
        tts_res = await engine.synthesize_speech(text="Bonjour monde")
        assert "audio_base64" in tts_res
        assert tts_res["format"] == "wav"

    asyncio.run(_run())
