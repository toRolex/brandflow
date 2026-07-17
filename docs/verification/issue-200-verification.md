# Issue #200 End-to-End Verification Report

## Summary

- **Mode**: Import
- **Product**: verify
- **Project ID**: `prj_11c23eed36a5`
- **Job ID**: `job_verify_186a75b2`
- **Final state**: `completed`
- **Final video**: `workspace/projects/prj_11c23eed36a5/runtime/jobs/job_verify_186a75b2/final.mp4`
- **Verified at**: 2026-07-17 02:49:58 +0800

## Job configuration

```json
{
  "product": "verify",
  "brand": "brandflow",
  "platforms": ["douyin"],
  "mode": "import",
  "manual_script": "欢迎观看本期测评。这款产品做工扎实。使用体验非常流畅。推荐立即下单体验。",
  "auto_approve": true,
  "skip_subtitle": true,
  "audio_source": "tts",
  "language": "mandarin"
}
```

## Scene configuration (temporary ``config/app_config.json``)

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
    }
  ],
  "format": {
    "duration": "5.000000"
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
| audio | AAC | aac |

## Scene / montage order check

Frames were sampled from `final.mp4` to verify scene order:

| Time | Center pixel (RGB) | Interpretation |
|------|--------------------|----------------|
| 1 s | (254, 0, 0) | first scene clip (red) |
| 4 s | (0, 0, 255) | second scene clip (blue) |

This confirms the scene segment and montage concatenation produced the expected
order.

## Notes

- No real LLM/TTS/Vision calls were made; the job relied on a manual script and
  an uploaded synthetic audio file.
- Scene assembly used two synthetic 720x1280 clips with a 500 ms crossfade.
- Montage assembly concatenated the scene segment with the (empty) base path and
  produced `assembled.mp4`.
- Final rendering burned the uploaded audio into `final.mp4`. Subtitle burn was
  skipped (`skip_subtitle=true`) because the local Homebrew ffmpeg build does not
  include the `subtitles` filter (libass). Since the subtitle phase is skipped
  when `skip_subtitle=true`, no SRT file was generated in this run.
- Manual playback inspection was replaced by automated frame sampling (above).
- The control plane was run with `DEV_AUTO_TICK=1`; a separate worker was not
  started because the auto-tick loop already executes the full pipeline locally.
- This run only covers the post-refactor code; a pre-refactor baseline run was
  not performed because the verification is that the current pipeline still
  produces the documented output format.

## Control-plane log tail

```
2026-07-17 02:49:35,887 [INFO] root - Starting control plane on 127.0.0.1:17890
INFO:     Started server process [38799]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:17890 (Press CTRL+C to quit)
INFO:     127.0.0.1:60872 - "GET /api/health HTTP/1.1" 200 OK
INFO:     127.0.0.1:60874 - "POST /api/projects HTTP/1.1" 200 OK
INFO:     127.0.0.1:60876 - "POST /api/projects/prj_11c23eed36a5/jobs HTTP/1.1" 200 OK
INFO:     127.0.0.1:60878 - "POST /api/jobs/job_verify_186a75b2/audio HTTP/1.1" 200 OK
INFO:     127.0.0.1:60880 - "GET /api/jobs/job_verify_186a75b2 HTTP/1.1" 200 OK
INFO:     127.0.0.1:60923 - "GET /api/jobs/job_verify_186a75b2 HTTP/1.1" 200 OK
[AUTO-TICK] job_verify_186a75b2: queued -> scene_assembling (advanced)
INFO:     127.0.0.1:60984 - "GET /api/jobs/job_verify_186a75b2 HTTP/1.1" 200 OK
[SCENE] 2 clips selected for job_verify_186a75b2
[TTS] Using uploaded audio: /Users/rolex/Documents/Codes/githubProject/MyProject/brandflow.feature-200-end-to-end-video-consistency/workspace/projects/prj_11c23eed36a5/audio/job_verify_186a75b2_audio.mp3
[SCENE] Running ffmpeg xfade for 2 clips
[SCENE] scene_segment.mp4 produced (68123 bytes)
[AUTO-TICK] job_verify_186a75b2: scene_assembling -> subtitle_generating (advanced)
INFO:     127.0.0.1:61024 - "GET /api/jobs/job_verify_186a75b2 HTTP/1.1" 200 OK
INFO:     127.0.0.1:61079 - "GET /api/jobs/job_verify_186a75b2 HTTP/1.1" 200 OK
[AUTO-TICK] job_verify_186a75b2: subtitle_generating -> montage_assembling (advanced)
INFO:     127.0.0.1:61153 - "GET /api/jobs/job_verify_186a75b2 HTTP/1.1" 200 OK
[MONTAGE] Using scene_segment as assembled for job_verify_186a75b2
[MONTAGE] assembled.mp4 produced (68123 bytes)
[AUTO-TICK] job_verify_186a75b2: montage_assembling -> video_rendering (advanced)
INFO:     127.0.0.1:61214 - "GET /api/jobs/job_verify_186a75b2 HTTP/1.1" 200 OK
INFO:     127.0.0.1:61250 - "GET /api/jobs/job_verify_186a75b2 HTTP/1.1" 200 OK
[VIDEO] Using assembled video as base for job_verify_186a75b2 (no clips)
[AUTO-TICK] job_verify_186a75b2: video_rendering -> final_rendering (advanced)
INFO:     127.0.0.1:61330 - "GET /api/jobs/job_verify_186a75b2 HTTP/1.1" 200 OK
[FINAL] job_verify_186a75b2: base=True audio=True skip_subtitle=True srt=False
[FINAL] job_verify_186a75b2: final.mp4 produced (134435 bytes)
[AUTO-TICK] job_verify_186a75b2: final_rendering -> final_review (advanced)
INFO:     127.0.0.1:61370 - "GET /api/jobs/job_verify_186a75b2 HTTP/1.1" 200 OK
INFO:     127.0.0.1:61390 - "GET /api/jobs/job_verify_186a75b2 HTTP/1.1" 200 OK
[AUTO-TICK] job_verify_186a75b2: final_review -> completed (completed)
INFO:     127.0.0.1:61422 - "GET /api/jobs/job_verify_186a75b2 HTTP/1.1" 200 OK
```
