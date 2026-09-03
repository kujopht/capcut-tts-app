"""OpenMontage-backed AnimationWorker - a provider-neutral, isolated
animation pipeline sitting behind Content Factory (not wired into any live
trigger yet - see worker.py's own module docstring for the exact scope
boundary: this package produces QA_PASS renders archived to Drive/R2, it
does not autonomously create or publish Novel/Chapter records).

The generation method (deterministic layered composition: separate
background + per-character generation, chroma-key extraction, Python
compositing) is FROZEN per the mission that validated it - never revert to
one-pass dual-character generation.

AGPL boundary: this package never imports OpenMontage/Remotion Python
code. remotion_render.py shells out to the Remotion CLI as a subprocess
with a JSON props file - the only integration path with the isolated
OpenMontage clone.
"""
