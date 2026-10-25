"""makable Shorts: a 1-minute vertical video about what changed in makable, made by stages that share a folder.

Each stage is a program of its own with its own packages (`shorts.stages`), reading and writing a video's run
folder under the names in `shorts.run`, the contract between them: record (the footage) -> write-script
(Gemini) -> film-intro (Gemini Omni) -> revoice-intro and speak (your voice, on a GPU) -> assemble (ffmpeg).
`shorts.orchestrator` runs what's due, each stage in a process of its own. The other modules are what the
stages use, and know nothing of run folders.
"""
