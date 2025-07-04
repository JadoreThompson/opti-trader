class MockLock:
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockPusher:
    def __init__(self):
        self.payloads = []

    def append(self, payload: dict, speed: str = "slow", channel: str = None):
        self.payloads.append(payload)