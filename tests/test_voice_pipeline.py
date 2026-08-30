"""Tests for Real-Time Voice-to-Voice Pipeline."""

import pytest

from openclaw_mesh.engines.voice_pipeline import RealTimeVoicePipeline, VoiceStreamConfig


@pytest.mark.asyncio
async def test_voice_pipeline_processing():
    pipeline = RealTimeVoicePipeline(VoiceStreamConfig(language="fr"))

    async def dummy_audio_generator():
        # Yield 3 PCM audio chunks
        for _ in range(3):
            yield b"\x00\x00\x7f\x7f" * 160

    events = [event async for event in pipeline.process_voice_turn(dummy_audio_generator())]

    event_types = [e["type"] for e in events]
    assert "transcription" in event_types
    assert "audio_response" in event_types
    assert "turn_complete" in event_types

    # Verify audio chunks format
    audio_events = [e for e in events if e["type"] == "audio_response"]
    assert len(audio_events) >= 1
    assert audio_events[0]["format"] == "audio/pcm"
    assert audio_events[0]["sample_rate"] == 16000
    assert audio_events[0]["audio_base64"]
