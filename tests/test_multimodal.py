import asyncio

import pytest

from openclaw_mesh.engines.multimodal import MultiModalEngine


def test_multimodal_vision():
    engine = MultiModalEngine()

    async def _run():
        # Test valid base64 payload
        res = await engine.analyze_image(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
            prompt="Describe this UI component",
        )
        assert "text" in res
        assert "backend" in res
        assert res["duration_ms"] >= 0

        # Test empty image raises ValueError
        with pytest.raises(ValueError, match="invalides ou vides"):
            await engine.analyze_image("")

    asyncio.run(_run())


def test_multimodal_stt_and_tts():
    engine = MultiModalEngine()

    async def _run():
        # 1. STT Whisper
        stt_res = await engine.transcribe_audio(
            audio_base64="UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=",
            language="fr",
        )
        assert "transcript" in stt_res
        assert stt_res["language"] == "fr"

        with pytest.raises(ValueError, match="vide"):
            await engine.transcribe_audio(audio_base64="")

        # 2. TTS Synthesizer
        tts_res = await engine.synthesize_speech(text="Bonjour monde OpenClawMesh")
        assert "audio_base64" in tts_res
        assert tts_res["sample_rate"] > 0

        with pytest.raises(ValueError, match="vide"):
            await engine.synthesize_speech(text="")

    asyncio.run(_run())
