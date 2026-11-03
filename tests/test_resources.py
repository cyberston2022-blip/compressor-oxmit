"""Dynamic worker CPU tuner: per-count core budgets and change-debouncing."""
from oxmit.resources import WorkerCpuTuner, cores_for
from oxmit.config import Settings


def test_cores_for_mapping():
    assert cores_for(0, 7.0, 3.2, 2.0) == 7.0
    assert cores_for(1, 7.0, 3.2, 2.0) == 7.0      # single job: whole machine
    assert cores_for(2, 7.0, 3.2, 2.0) == 3.2      # split per user spec
    assert cores_for(3, 7.0, 3.2, 2.0) == 2.33
    assert cores_for(4, 7.0, 3.2, 2.0) == 2.0      # floor holds


class FakeApi:
    def __init__(self, updates):
        self.updates = updates

    def _url(self, path):
        return path

    def _post_json(self, url, data):
        self.updates.append((url, data))

        class R:
            status_code = 200
        return R()

    def _raise_for_status(self, res):
        pass


class FakeContainers:
    def __init__(self):
        self.updates = []

    def get(self, name):
        updates = self.updates

        class C:
            id = "cid-" + name

        return C()


class FakeClient:
    def __init__(self):
        self.updates = []
        self.containers = FakeContainers()
        self.api = FakeApi(self.updates)


async def test_tuner_applies_on_change_only():
    cfg = Settings(worker_cpu_single=7.0, worker_cpu_multi=3.2,
                   worker_cpu_min=2.0,
                   worker_container_names=("w1", "w2"))
    client = FakeClient()
    tuner = WorkerCpuTuner(cfg)
    tuner._client = client

    await tuner.tune(1)   # 0 -> 7.0: apply
    assert len(client.updates) == 2
    assert all(u[1] == {"NanoCPUs": int(7.0 * 1e9)} for u in client.updates)

    await tuner.tune(1)   # same target: debounced
    assert len(client.updates) == 2

    await tuner.tune(2)   # 7.0 -> 3.2: apply
    assert all(u[1] == {"NanoCPUs": int(3.2 * 1e9)} for u in client.updates[-2:])

    await tuner.tune(0)   # idle -> back to max cap
    assert all(u[1] == {"NanoCPUs": int(7.0 * 1e9)} for u in client.updates[-2:])


async def test_tuner_disabled_without_socket(monkeypatch):
    cfg = Settings(worker_container_names=("w1",))
    monkeypatch.setattr("oxmit.resources.os.path.exists", lambda p: False)
    tuner = WorkerCpuTuner(cfg)
    client = FakeClient()
    tuner._client = None
    monkeypatch.setattr(tuner, "_get_client", lambda: None)
    await tuner.tune(1)   # must not raise
    assert tuner._last is None
