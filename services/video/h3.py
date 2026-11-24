"""MiniMax H3, the request a client sends, and the WanGP settings it becomes.

H3 makes a video and its 32 kHz stereo audio together (speech with lip sync, sound effects, music) from text, a start
image, first and last frames, or reference images of the people and things in it, with a voice to clone. WanGP
(github.com/deepbeepmeep/Wan2GP) runs it; `engine.py` hands it the settings `settings()` makes here.

The prompt builder follows H3's prompt contract as the "MiniMax H3 Turbo (INT8)" Kaggle notebook by AIQUEST Academy
(Apache 2.0) writes it: a scene, an exact spoken line, sound effects and music become H3's structured sections. A
prompt that's already structured (it has `integrated_multimodal_description:`, `detailed_description:` or
`subject_definitions:`) is sent as it is.

Nothing here imports torch, WanGP or Modal, so the API and the tests use it as they are.
"""

import math
import random
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, field_validator

# The PDMD 4-step LoRA (the Kaggle notebook's default) isn't offered: its keys are in diffusers' names, which WanGP's
# loader rejects ("unexpected module keys"); the notebook converts them with a loader of its own.
PDMD_LORA = "https://huggingface.co/pdmd2026/pdmd_4NFE_lora/resolve/main/lora_model_0.safetensors"


@dataclass(frozen=True)
class Model:
    """One of the H3 models the API offers: WanGP's model type, its steps and sampler, and what it takes."""

    model_type: str
    description: str
    steps: int
    sampler: str = "euler"
    references: bool = False  # Ref2VA: reference images and voices; FL2VA: start and end frames, a soundtrack
    loras: tuple[tuple[str, float], ...] = ()  # always applied (a distillation LoRA), as (url, strength)
    shift: float | None = None  # flow shift, when the model wants another than WanGP's default for it


MODELS = {
    "pdd": Model(
        "minimax_h3_fl2va_pruned_pdd",
        "WanGP's PDD 8-step model: text, start image, first + last frame, soundtrack. The fastest.",
        steps=8,
    ),
    "base": Model(
        "minimax_h3_fl2va_pruned",
        "Base H3, undistilled: text, start image, first + last frame, soundtrack. Slowest, for comparisons.",
        steps=20,
    ),
    "ref-pdd": Model(
        "minimax_h3_ref2va_pruned_pdd",
        "Ref2VA PDD 8-step: up to 3 reference images of people or things, and a voice to clone.",
        steps=8,
        references=True,
    ),
    "ref": Model(
        "minimax_h3_ref2va_pruned",
        "Ref2VA, undistilled: up to 3 reference images and a voice to clone. Slowest.",
        steps=20,
        references=True,
    ),
}
DEFAULT_MODEL = "pdd"

RESOLUTIONS = {"360p": (640, 352), "480p": (832, 480), "540p": (960, 544), "720p": (1280, 704)}  # 16:9's
ASPECTS = {"auto": None, "16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4, "21:9": 21 / 9}
DURATIONS = {3: 73, 4.5: 107, 5: 124, 6.5: 158, 8: 192, 10: 243, 12: 294, 15: 362}  # seconds: frames, at 24 fps
FPS = 24
MAX_REFERENCES = 3
LANGUAGES = ("English", "Chinese", "Spanish", "French", "German", "Japanese", "Korean", "Hindi", "Urdu", "Arabic",
             "Portuguese", "Russian", "Italian", "Turkish", "Indonesian")
STRUCTURED = re.compile(r"(integrated_multimodal_description:|detailed_description:|subject_definitions:)")

LORAS = {  # popular H3 LoRAs, by a short name: (url, strength, trigger words), as the Kaggle notebook lists them
    "realism-people": ("https://huggingface.co/fal/MiniMax-H3-Realism-People-LoRA/resolve/main/"
                       "h3-realism-people-t2v-i2v-r2v.safetensors", 1.0, "r34l1sm"),
    "camera-motion": ("https://huggingface.co/Jojocodex/minimax-h3-Camera-Motion-lora/resolve/main/"
                      "camera_motion_h3_lora_v1_3000_pruned.safetensors", 0.9, "camera motion"),
    "orbit-360": ("https://huggingface.co/pablodawson/MiniMax-H3-360-Orbit-LoRA/resolve/main/"
                  "minimax_h3_flf2v_lora_v1.safetensors", 1.0,
                  "One frozen instant. Only the camera moves. In a continuous 360 orbit."),
    "weapon-combat": ("https://huggingface.co/JOKER141/MiniMax-H3-Weapon-Combat-LoRA/resolve/main/"
                      "Bunny_weapon_combatV1.safetensors", 1.0, "BUNNY"),
    "spatial-physics": ("https://huggingface.co/Jojocodex/minimax-h3-spatial-physics-lora/resolve/main/"
                        "wushu_spatial_physics_clean_3000_pruned.safetensors", 0.4, ""),
    "face-speech": ("https://huggingface.co/vpakarinen/natural-face-speech-h3-lora/resolve/main/"
                    "natural_face_speech_h3_lora_v2_500.safetensors", 0.7, ""),
    "studio-1939": ("https://huggingface.co/lovis93/studio-1939-old-animation-lora-minimax-h3/resolve/main/"
                    "studio1939-light.safetensors", 1.0, "gulliv3r,"),
    "anime-motion": ("https://huggingface.co/prithivMLmods/MiniMax-H3-I2V-Anime-Motion-LoRA/resolve/main/"
                     "MiniMax-H3-I2V-Anime-Motion-LoRA-1400.safetensors", 1.0, "Anime-Motion"),
    "vhs-tape": ("https://huggingface.co/KennethFal/vh5tape-vhs-lora-minimax-h3/resolve/main/vh5tape.safetensors",
                 1.0, "vh5tape, worn VHS tape recording with visible tape damage."),
}
LORA_URL = re.compile(r"https://huggingface\.co/[\w.-]+/[\w.-]+/resolve/[^\s?#]+\.safetensors")


class Lora(BaseModel):
    """A LoRA: a name from LORAS or a Hugging Face .safetensors link (https://huggingface.co/…/resolve/…)."""

    name: str
    strength: float | None = Field(None, ge=-2, le=2)  # None: the LoRA's own (1 for a link)

    @field_validator("name")
    @classmethod
    def known(cls, name: str) -> str:
        if name not in LORAS and not LORA_URL.fullmatch(name):
            raise ValueError(f"{name!r}: one of {', '.join(LORAS)}, or a https://huggingface.co/…/resolve/….safetensors link")
        return name


class VideoRequest(BaseModel):
    """What to make. Media (start/end image, references, voice, soundtrack) come as files next to it."""

    prompt: str = ""  # the scene and action, or a whole structured H3 prompt
    dialogue: str = ""  # the exact words said, lip-synced
    language: str = "English"
    sound: str = ""  # sound effects and ambience
    music: str = ""  # music under it ("" for none)
    model: str = DEFAULT_MODEL
    resolution: str = "480p"
    aspect: str = "auto"  # auto: the first image's, else 16:9
    duration: float = 5  # seconds: one of DURATIONS
    steps: int | None = Field(None, ge=1, le=50)  # None: the model's
    seed: int | None = Field(None, ge=0, lt=2**31)  # None: a random one
    shift: float | None = Field(None, gt=0, le=30)  # None: the model's
    reference_names: list[str] = []  # what each reference is ("the girl", "the red car"), in order
    loras: list[Lora] = Field([], max_length=4)
    trigger_words: bool = True  # put the LoRAs' trigger words at the start of the prompt

    @field_validator("model")
    @classmethod
    def model_known(cls, value: str) -> str:
        if value not in MODELS:
            raise ValueError(f"{value!r}: one of {', '.join(MODELS)}")
        return value

    @field_validator("resolution")
    @classmethod
    def resolution_known(cls, value: str) -> str:
        if value not in RESOLUTIONS:
            raise ValueError(f"{value!r}: one of {', '.join(RESOLUTIONS)}")
        return value

    @field_validator("aspect")
    @classmethod
    def aspect_known(cls, value: str) -> str:
        if value not in ASPECTS:
            raise ValueError(f"{value!r}: one of {', '.join(ASPECTS)}")
        return value

    @field_validator("duration")
    @classmethod
    def duration_known(cls, value: float) -> float:
        if value not in DURATIONS:
            raise ValueError(f"{value!r} seconds: one of {', '.join(f'{d:g}' for d in DURATIONS)}")
        return value

    @field_validator("language")
    @classmethod
    def language_known(cls, value: str) -> str:
        found = next((name for name in LANGUAGES if name.lower() == value.strip().lower()), None)
        if found is None:
            raise ValueError(f"{value!r}: one of {', '.join(LANGUAGES)}")
        return found


@dataclass
class Media:
    """The files a request came with, as paths on the machine that runs it (or None)."""

    start_image: str | None = None
    end_image: str | None = None
    references: list[str] = field(default_factory=list)
    voice: str | None = None  # a voice to clone (Ref2VA): at least 2 seconds
    soundtrack: str | None = None  # audio the video follows and keeps, such as narration (FL2VA)
    sizes: dict[str, tuple[int, int]] = field(default_factory=dict)  # path: (width, height) of each image


def problems(request: VideoRequest, media: Media) -> list[str]:
    """Why this request can't be made (nothing: it can), checked before a GPU is spent on it."""
    model = MODELS[request.model]
    found = []
    if not request.prompt.strip() and not media.references and media.start_image is None:
        found.append("Write a prompt (or send a start image or references)")
    if model.references:
        if media.soundtrack:
            found.append(f"{request.model} takes a voice to clone, not a soundtrack: use pdd or base")
        if media.voice and not media.references:
            found.append("A voice needs at least one reference image: H3 binds each voice to a reference")
    else:
        if media.references:
            found.append(f"References need a reference model: ref-pdd or ref (not {request.model})")
        if media.voice:
            found.append("A voice to clone needs ref-pdd or ref; to keep audio as it is, send it as the soundtrack")
    if len(media.references) > MAX_REFERENCES:
        found.append(f"At most {MAX_REFERENCES} references")
    return found


def size(request: VideoRequest, media: Media) -> tuple[int, int]:
    """The video's width and height: the resolution's area in the aspect (auto: the first image's), on 32 px."""
    width, height = RESOLUTIONS[request.resolution]
    ratio = ASPECTS[request.aspect]
    if ratio is None:
        first = next((media.sizes.get(p) for p in [media.start_image, media.end_image, *media.references] if p), None)
        ratio = first[0] / first[1] if first else 16 / 9
    area = width * height
    w = max(256, round(math.sqrt(area * ratio) / 32) * 32)
    h = max(256, round(area / w / 32) * 32)
    return w, h


def triggers(request: VideoRequest) -> list[str]:
    return [LORAS[lora.name][2] for lora in request.loras if lora.name in LORAS and LORAS[lora.name][2]]


def build_prompt(request: VideoRequest, media: Media) -> str:
    """H3's prompt for this request: its sections, picture anchors and subject definitions."""
    scene = request.prompt.strip()
    words = [t for t in (triggers(request) if request.trigger_words else []) if t.lower() not in scene.lower()]
    if STRUCTURED.search(scene):  # a whole H3 prompt already: only the trigger words go in front
        return (" ".join(words) + " " + scene).strip() if words else scene
    trigger = "".join(t + (" " if t[-1] in ".,;:" else ", ") for t in words)
    seconds = DURATIONS[request.duration] / FPS
    secs = f"{request.duration:g}"
    refs = len(media.references)
    speaker = "<Subject 1>" if refs else "The main character"
    line = ""
    if request.dialogue.strip():
        voice = " in the voice from <Audio 1>" if media.voice else ""
        line = (f" {speaker} speaks clearly{voice} with natural, synchronized lip movements and says "
                f"(S1) <d>[{request.language}] {request.dialogue.strip()}</d>")
    elif media.soundtrack:
        line = f" {speaker} speaks with natural lip movements synchronized to the speech."
    sound = request.sound.strip() or "Natural ambient sound that matches the scene and the visible action."
    music = request.music.strip() or "N/A"
    pictures, anchors = 0, []
    if media.start_image:
        pictures += 1
        anchors.append(f"For the target video, at 0.00 seconds into the target video, <Picture {pictures}> "
                       "(from [Shot 1]) is fully referenced.")
    if media.end_image:
        pictures += 1
        anchors.append(f"For the target video, at {seconds:.2f} seconds into the target video, <Picture {pictures}> "
                       "(from [Shot 1]) is fully referenced.")
    if not refs:
        lead = ("Continue directly from <Picture 1>, preserving its subject, composition and lighting. "
                if media.start_image else "")
        body = (f"integrated_multimodal_description: [Shot 1] {trigger}A {secs}-second cinematic single take. "
                f"{lead}{scene}{line}\noverall_soundscape: {sound}\nnon_diegetic_music: {music}")
        return "\n".join([*anchors, body])
    names = [n.strip() for n in request.reference_names]  # by position: an empty one gets the fallback
    subjects, retention = [], []
    for i in range(refs):
        label = (names[i] if i < len(names) else "") or ("the main subject" if i == 0 else "the subject")
        subjects.append(f"<Subject {i + 1}> is {label} in <Picture {pictures + i + 1}>, preserving their exact "
                        "identity, appearance, proportions, clothing and distinctive details.")
        retention.append(f"<Subject {i + 1}> (appears in [Shot 1]): fully_preserved - identity and appearance are "
                         "retained; the setting, action, camera and lighting are new.")
    if media.voice:
        retention.append("<Audio 1>: reference - the voice timbre and delivery of <Subject 1> follow <Audio 1>.")
    task = "[reference generation + audio reference]" if media.voice else "[reference generation]"
    return "\n".join([
        *anchors,
        "subject_definitions:", *subjects,
        "summary:", f"{task} {scene}",
        "retention_analysis:", *retention,
        "detailed_description:",
        f"{trigger}The target video is a {secs}-second cinematic single take. [Shot 1] {scene}{line} Identities, "
        "motion and lighting remain stable and physically coherent.",
        f"overall_soundscape: {sound}",
        f"non_diegetic_music: {music}",
    ])


def loras(request: VideoRequest) -> list[tuple[str, float]]:
    """(url, strength) of every LoRA to apply: the model's own, then the request's."""
    chosen = list(MODELS[request.model].loras)
    for lora in request.loras:
        url, strength, _ = LORAS.get(lora.name, (lora.name, 1.0, ""))
        if lora.strength != 0:
            chosen.append((url, strength if lora.strength is None else lora.strength))
    return chosen


def settings(request: VideoRequest, media: Media, seed: int | None = None) -> dict:
    """WanGP's settings for this request (laid over the model's defaults by the engine)."""
    model = MODELS[request.model]
    width, height = size(request, media)
    chosen = loras(request)
    out = {
        "model_type": model.model_type,
        "prompt": build_prompt(request, media),
        "resolution": f"{width}x{height}",
        "video_length": DURATIONS[request.duration],
        "num_inference_steps": request.steps or model.steps,
        "sample_solver": model.sampler,
        "guidance_phases": 1,
        "seed": seed if seed is not None else (request.seed if request.seed is not None else random.randrange(2**31)),
        "activated_loras": [url for url, _ in chosen],
        "loras_multipliers": " ".join(f"{strength:g}" for _, strength in chosen),
    }
    if request.shift or model.shift:
        out["flow_shift"] = request.shift or model.shift
    image_prompt = ("S" if media.start_image else "") + ("E" if media.end_image else "")
    out["image_prompt_type"] = image_prompt or "T"
    if media.start_image:
        out["image_start"] = media.start_image
    if media.end_image:
        out["image_end"] = media.end_image
    if media.references:
        out["image_refs"] = list(media.references)
        out["video_prompt_type"] = "I"
        out["image_refs_relative_size"] = 100
    if media.voice:
        out.update(audio_guide=media.voice, audio_prompt_type="A")
    elif media.soundtrack:
        out.update(audio_guide=media.soundtrack, audio_prompt_type="A")
    return out
