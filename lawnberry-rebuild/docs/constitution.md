# Constitutional Bootstrap

- Platform: Raspberry Pi OS Bookworm (64-bit), Python 3.11.x
- AI package isolation: pycoral/edgetpu banned in main env; Coral in isolated venv-coral
- Resource ownership: camera-stream.service exclusively owns camera; other services consume via IPC

Refer to `/.specify/memory/constitution.md` for governing rules.
