# Minimal psutil stub for tests to patch or use basic memory info

class _MemInfo:
    rss = 50 * 1024 * 1024

class _Process:
    def __init__(self, pid):
        self.pid = pid
    def memory_info(self):
        return _MemInfo()

def Process(pid):  # pragma: no cover
    return _Process(pid)
