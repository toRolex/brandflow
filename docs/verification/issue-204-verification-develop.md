# Issue #204 End-to-End Verification Report — Run: develop

## Summary

- **Mode**: Import
- **Run label**: develop
- **Product**: verify
- **Project ID**: `prj_5554a6efeb87`
- **Job ID**: `job_verify_7556bfd1`
- **Final state**: `completed`
- **Final video**: `workspace/projects/prj_5554a6efeb87/runtime/jobs/job_verify_7556bfd1/final.mp4`
- **File size**: 121330 bytes
- **ffmpeg subtitles filter**: YES
- **Verified at**: 2026-07-17 04:17:58 +0800

## Job configuration

```json
{
  "product": "verify",
  "brand": "brandflow",
  "platforms": ["douyin"],
  "mode": "import",
  "manual_script": "欢迎观看本期测评。这款产品做工扎实。使用体验非常流畅。推荐立即下单体验。",
  "auto_approve": true,
  "audio_source": "tts",
  "language": "mandarin"
}
```

## Scene configuration

```json
{
  "folders": [
    {
      "path": "verify/scene1"
    },
    {
      "path": "verify/scene2"
    }
  ],
  "transition_duration_ms": 500
}
```

## State-machine phases observed

```
queued -> scene_assembling -> subtitle_generating -> montage_assembling -> video_rendering -> final_rendering -> final_review -> completed
```

## Artifacts in job directory

```
assembled.mp4
audio.mp3
base.mp4
final.mp4
scene_segment.mp4
subtitles.srt
verify口播文案.txt
```

## ffprobe output (final.mp4)

```json
{
  "programs": [],
  "stream_groups": [],
  "streams": [
    {
      "codec_name": "h264",
      "width": 720,
      "height": 1280,
      "pix_fmt": "yuv420p",
      "r_frame_rate": "30/1",
      "avg_frame_rate": "30/1"
    },
    {
      "codec_name": "aac",
      "sample_rate": "24000",
      "channels": 1,
      "r_frame_rate": "0/0",
      "avg_frame_rate": "0/0"
    }
  ],
  "format": {
    "duration": "5.500000",
    "size": "121330",
    "bit_rate": "176480"
  }
}
```

## Format check

| Field | Expected | Actual |
|-------|----------|--------|
| width | 720 | 720 |
| height | 1280 | 1280 |
| codec | libx264 (h264) | h264 |
| pix_fmt | yuv420p | yuv420p |
| fps | 30 | 30/1 |
| audio | AAC | N/A |

## Scene / montage order check

| Time | Center pixel (RGB) | Interpretation |
|------|--------------------|----------------|
| 1 s | (254, 0, 0) | first scene clip (red) |
| 4 s | (0, 0, 255) | second scene clip (blue) |

## Control-plane log tail

```
2026-07-17 04:17:31,468 [INFO] root - Starting control plane on 127.0.0.1:17890
INFO:     Started server process [38037]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:17890 (Press CTRL+C to quit)
INFO:     127.0.0.1:59868 - "GET /api/health HTTP/1.1" 200 OK
INFO:     127.0.0.1:59870 - "POST /api/projects HTTP/1.1" 200 OK
INFO:     127.0.0.1:59872 - "POST /api/projects/prj_5554a6efeb87/jobs HTTP/1.1" 200 OK
INFO:     127.0.0.1:59874 - "GET /api/jobs/job_verify_7556bfd1 HTTP/1.1" 200 OK
INFO:     127.0.0.1:59884 - "GET /api/jobs/job_verify_7556bfd1 HTTP/1.1" 200 OK
[AUTO-TICK] job_verify_7556bfd1: queued -> scene_assembling (advanced)
INFO:     127.0.0.1:59903 - "GET /api/jobs/job_verify_7556bfd1 HTTP/1.1" 200 OK
[TTS DEBUG] Qwen TTS: model=qwen-tts text_len=36
[SCENE] 2 clips selected for job_verify_7556bfd1
[SCENE] Running ffmpeg xfade for 2 clips
[SCENE] scene_segment.mp4 produced (68123 bytes)
[TTS] Synthesized: True, size=382124
[AUTO-TICK] job_verify_7556bfd1: scene_assembling -> subtitle_generating (advanced)
INFO:     127.0.0.1:59921 - "GET /api/jobs/job_verify_7556bfd1 HTTP/1.1" 200 OK
INFO:     127.0.0.1:60014 - "GET /api/jobs/job_verify_7556bfd1 HTTP/1.1" 200 OK
[SUBTITLE] Building SRT: audio=audio.mp3 duration=7.96s script_len=36
[AUTO-TICK] job_verify_7556bfd1: subtitle_generating -> montage_assembling (advanced)
INFO:     127.0.0.1:60031 - "GET /api/jobs/job_verify_7556bfd1 HTTP/1.1" 200 OK
INFO:     127.0.0.1:60044 - "GET /api/jobs/job_verify_7556bfd1 HTTP/1.1" 200 OK
[MONTAGE] Using scene_segment as assembled for job_verify_7556bfd1
[MONTAGE] assembled.mp4 produced (68123 bytes)
[AUTO-TICK] job_verify_7556bfd1: montage_assembling -> video_rendering (advanced)
INFO:     127.0.0.1:60047 - "GET /api/jobs/job_verify_7556bfd1 HTTP/1.1" 200 OK
[VIDEO] Using assembled video as base for job_verify_7556bfd1 (no clips)
[AUTO-TICK] job_verify_7556bfd1: video_rendering -> final_rendering (advanced)
INFO:     127.0.0.1:60057 - "GET /api/jobs/job_verify_7556bfd1 HTTP/1.1" 200 OK
INFO:     127.0.0.1:60075 - "GET /api/jobs/job_verify_7556bfd1 HTTP/1.1" 200 OK
[FINAL] job_verify_7556bfd1: base=True audio=True skip_subtitle=False srt=True
[FINAL] job_verify_7556bfd1: final.mp4 produced (121330 bytes)
[AUTO-TICK] job_verify_7556bfd1: final_rendering -> final_review (advanced)
INFO:     127.0.0.1:60083 - "GET /api/jobs/job_verify_7556bfd1 HTTP/1.1" 200 OK
[AUTO-TICK] job_verify_7556bfd1: final_review -> completed (completed)
INFO:     127.0.0.1:60108 - "GET /api/jobs/job_verify_7556bfd1 HTTP/1.1" 200 OK
```
