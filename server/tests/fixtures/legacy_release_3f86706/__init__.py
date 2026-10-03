"""
FROZEN COPY of the AI control plane as it runs in PRODUCTION today — `model.py` and `store.py` of commit 3f86706 (the release
before Alibaba Model Studio), verbatim (line endings aside), except for ONE changed line: the `from ... .model import` in `store.py` points at
this package instead of `server.ai_assistant.control.model`.

Purpose: a code ROLLBACK test that is not a simulation. `test_ai_alibaba_isolation.py` writes configuration with the NEW code and
then loads the very same stored rows with THIS old code and its old validation — exactly what a rollback of the deployment does.
Do not edit these two files and do not "modernise" them; if they ever need to change, the rollback guarantee they stand for
needs to be re-argued, not the fixture adjusted.

    git show 3f86706:server/ai_assistant/control/model.py   ==  model.py
    git show 3f86706:server/ai_assistant/control/store.py   ==  store.py  (import line only differs)
"""
