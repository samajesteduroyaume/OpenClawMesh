"""Tests for Real-Time Video Stream Processor (30 FPS)."""

from openclaw_mesh.engines.video_stream import RealTimeVideoProcessor


def test_video_stream_ingest_and_keyframes():
    processor = RealTimeVideoProcessor(keyframe_interval=5)

    # Ingest 15 video frames (should generate 3 keyframes)
    for i in range(15):
        frame_bytes = f"FRAME_DATA_{i}".encode().ljust(512, b"\x00")
        frame = processor.ingest_frame(frame_bytes=frame_bytes, width=1280, height=720)
        assert frame.frame_index == i + 1

    summary = processor.get_stream_summary()
    assert summary.total_frames_processed == 15
    assert summary.keyframes_extracted == 3
    assert summary.fps_average == 30.0

    # Query visual context
    query_res = processor.query_visual_context("Que voit l'agent dans la pièce ?")
    assert query_res["keyframes_analyzed"] == 3
    assert query_res["confidence"] > 0.9
