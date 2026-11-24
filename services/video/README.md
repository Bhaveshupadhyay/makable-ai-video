# Video API: MiniMax H3 on Modal

MiniMax H3 makes video and its 32 kHz stereo audio together: speech with lip sync, sound effects and music. You can
start it from text, a start image, first + last frames, reference images of people or things (with a voice to clone),
or a soundtrack the video follows, such as your narration. [WanGP](https://github.com/deepbeepmeep/Wan2GP) runs it on
one H100. The prompt builder follows the *MiniMax H3 Turbo (INT8)* Kaggle notebook by AIQUEST Academy.

| File | What it is |
|---|---|
| `h3.py` | The models, the request, H3's prompt contract, and the WanGP settings a request becomes |
| `api.py` | The HTTP API (FastAPI), as jobs |
| `engine.py` | WanGP's Python API on the GPU |
| `app.py` | Modal: the GPU class, the web endpoint, the Volumes and the jobs Dict |
| `client.py` | A Python client and a command line |

## Deploy

```bash
modal secret create makable-video VIDEO_API_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
```

```bash
modal deploy -m services.video.app
```

Set `VIDEO_API_URL` (the `…modal.run` address it prints) and `VIDEO_API_KEY` wherever you call it from. The first
video with each model downloads its weights into the `makable-video-models` Volume (~30 to 60 GB, several minutes).
After that, a new container only loads them.

**Cost:** an H100 on Modal is about $4 an hour while it works, plus `IDLE` (5 minutes) after the last job. Nothing
runs between videos.

## Models

| `model` | Takes | Steps |
|---|---|---|
| `pdd` (default) | text, `start_image`, `end_image`, `soundtrack` | 8 |
| `base` | the same, undistilled | 20 |
| `ref-pdd` | text, `references` (up to 3), `voice` | 8 |
| `ref` | the same, undistilled | 20 |

* **Resolutions:** `360p`, `480p` (the default), `540p` and `720p`.
* **Aspects:** `auto` (the first image's shape), `16:9`, `9:16`, `1:1`, `4:3`, `3:4` and `21:9`.
* **Durations:** 3, 4.5, 5, 6.5, 8, 10, 12 and 15 seconds, at 24 fps.

## Calls

Every call except `/health` needs the key, as `Authorization: Bearer $VIDEO_API_KEY`.

Text to video:

```bash
curl -s $VIDEO_API_URL/v1/videos -H "Authorization: Bearer $VIDEO_API_KEY" -H 'content-type: application/json' \
  -d '{"prompt": "A fox news anchor in a tiny studio", "dialogue": "Good evening, forest.", "aspect": "9:16"}'
```

It answers `202` with `{"id": "vid_…", "status": "queued", "seed": …, "width": 480, "height": 832, "prompt": …}`.

With files, send multipart: the request as JSON in `request`, plus any of `start_image`, `end_image`,
`references` (repeat the field), `voice` and `soundtrack`:

```bash
curl -s $VIDEO_API_URL/v1/videos -H "Authorization: Bearer $VIDEO_API_KEY" \
  -F 'request={"prompt": "She turns to the camera and smiles", "aspect": "9:16"}' \
  -F start_image=@still.png -F soundtrack=@narration.wav
```

Then check on it, and download it once `status` is `succeeded`:

```bash
curl -s $VIDEO_API_URL/v1/videos/vid_… -H "Authorization: Bearer $VIDEO_API_KEY"
```

```bash
curl -s $VIDEO_API_URL/v1/videos/vid_…/content -H "Authorization: Bearer $VIDEO_API_KEY" -o clip.mp4
```

| Call | Does |
|---|---|
| `GET /health` | Answers without a key |
| `GET /v1/models` | Lists the models, resolutions, aspects, durations and languages |
| `GET /v1/loras` | Lists the LoRAs you can name. Any `https://huggingface.co/…/resolve/….safetensors` link works too |
| `POST /v1/prompts` | Shows the H3 prompt and WanGP settings a request would run with, without spending GPU time |
| `POST /v1/videos` | Starts a job |
| `GET /v1/videos` | Lists the latest jobs (`?limit=`) |
| `GET /v1/videos/{id}` | `status` (`queued`, `running`, `succeeded`, `failed` or `cancelled`), `progress` from 0 to 1, `phase`, `error` and `timings` |
| `GET /v1/videos/{id}/content` | Returns the MP4 |
| `POST /v1/videos/{id}/cancel` | Cancels the job |
| `DELETE /v1/videos/{id}` | Deletes the job and its MP4 |

### Request fields

| Field | What it is |
|---|---|
| `prompt` | The scene and action, or a whole structured H3 prompt, which is sent as it is |
| `dialogue` | The exact words spoken, lip-synced |
| `language` | The language of `dialogue` |
| `sound` | Sound effects and ambience |
| `music` | Background music |
| `model`, `resolution`, `aspect`, `duration` | See **Models** |
| `steps`, `seed`, `shift` | Override the model's defaults |
| `reference_names` | What each reference is: `["the girl", "the red car"]` |
| `loras` | `[{"name": "camera-motion"}, {"name": "<HF link>", "strength": 0.8}]` |
| `trigger_words` | Puts each LoRA's trigger words at the start of the prompt (on by default) |

## Python and the command line

```python
from services.video.client import VideoClient

client = VideoClient()  # VIDEO_API_URL, VIDEO_API_KEY
job = client.create({"prompt": "…", "aspect": "9:16"}, start_image="still.png")
client.download(client.wait(job["id"])["id"], "clip.mp4")
```

```bash
python -m services.video.client make "A fox reads the news" --dialogue "Good evening." --aspect 9:16 -o fox.mp4
```

## Licence

WanGP's licence lets you use it for free, including inside a company, and you may sell what you make with it. You
may not offer *paid* API or hosted access to WanGP without its author's commercial licence. This API is for your own
videos. Check each model's and LoRA's own licence on its Hugging Face page.
