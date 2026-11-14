"""Dynamic worker CPU tuner — per-replica pool semantics (V3 §17).

The tuner writes the SAME NanoCPU value to every replica, so per-worker
allocation is capped at WORKER_CPU_SINGLE / replicas. This makes overcommit
structurally impossible (regression: 3 x 4.5 = 13.5 requested on 8 vCPU
dropped aggregate throughput from ~104 to ~74 FPS on the Ohio benchmark).
"""
from types import SimpleNamespace

from oxmit.resources import WorkerCpuTuner, cores_for
from oxmit.config import Settings


def test_cores_for_two_replicas_never_exceed_pool():
    # pool=4.5 across 2 replicas -> 2.25 per worker, always
    assert cores_for(0, 4.5, 2, 1.5) == 2.25
    assert cores_for(1, 4.5, 2, 1.5) == 2.25
    assert cores_for(2, 4.5, 2, 1.5) == 2.25


def test_cores_for_three_replicas_no_overcommit():
    # REGRESSION (Ohio benchmark): pool=4.5 across 3 replicas used to return
    # 4.5 per worker (13.5 total on an 8-vCPU host) and LOST throughput.
    assert cores_for(0, 4.5, 3, 1.5) == 1.5
    assert cores_for(1, 4.5, 3, 1.5) == 1.5
    assert cores_for(3, 4.5, 3, 1.5) == 1.5


def test_cores_for_single_replica_gets_whole_pool():
    assert cores_for(0, 4.5, 1, 1.5) == 4.5
    assert cores_for(1, 4.5, 1, 1.5) == 4.5
    assert cores_for(2, 4.5, 1, 1.5) == 2.25   # active > replicas shares down
    assert cores_for(6, 4.5, 1, 1.5) == 1.5    # floor holds


def test_cores_for_floor_is_capped_by_pool_share():
    # A floor above the per-replica share must NOT break the pool budget.
    assert cores_for(2, 4.5, 3, 2.0) == 1.5


class FakeApi:
    """Mimics the docker SDK low-level container-update API the tuner uses.

    The tuner posts {"NanoCPUs": ...} through api._url/_post_json on
    purpose: docker-py 7.x update_container() does not expose NanoCPUs and
    cpu_period/cpu_quota conflict with compose-set NanoCPUs.
    """

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
        self.calls = 0

    def get(self, name):
        self.calls += 1
        if self.calls == 1 and getattr(self, "fail_first", False):
            raise RuntimeError("transient docker error")
        return SimpleNamespace(id="cid-" + name)


class FakeClient:
    def __init__(self, fail_first=False):
        self.updates = []
        self.api = FakeApi(self.updates)
        self.containers = FakeContainers()
        self.containers.fail_first = fail_first


async def test_tuner_applies_on_change_only():
    # pool=9.0 / 2 replicas -> 4.5 each; active>2 shares down to 3.0.
    cfg = Settings(worker_cpu_single=9.0, worker_cpu_multi=3.2,
                   worker_cpu_min=1.5,
                   worker_container_names=("w1", "w2"))
    client = FakeClient()
    tuner = WorkerCpuTuner(cfg)
    tuner._client = client

    await tuner.tune(1)   # -> 4.5 per worker: apply
    assert len(client.updates) == 2
    assert all(u[1] == {"NanoCPUs": int(4.5 * 1e9)} for u in client.updates)
    assert all("/containers/cid-" in u[0] and u[0].endswith("/update")
               for u in client.updates)

    await tuner.tune(1)   # same target: debounced
    assert len(client.updates) == 2

    await tuner.tune(3)   # 3 active on 2 replicas -> 3.0: apply
    assert all(u[1] == {"NanoCPUs": int(3.0 * 1e9)} for u in client.updates[-2:])

    await tuner.tune(0)   # idle -> back to per-replica cap
    assert all(u[1] == {"NanoCPUs": int(4.5 * 1e9)} for u in client.updates[-2:])


async def test_tuner_retries_partial_update():
    """If only some workers take the update, the target is not marked as
    applied - the next poll retries (idempotent container update)."""
    cfg = Settings(worker_cpu_single=9.0, worker_cpu_multi=3.2,
                   worker_cpu_min=1.5,
                   worker_container_names=("w1", "w2"))
    client = FakeClient(fail_first=True)   # first .get() fails (w1)
    tuner = WorkerCpuTuner(cfg)
    tuner._client = client

    await tuner.tune(1)
    assert len(client.updates) == 1        # only w2 updated
    assert tuner._last is None             # partial update: not debounced away

    await tuner.tune(1)                    # retried on the next poll
    assert len(client.updates) == 3        # w1 retried + w2 again
    assert all(u[1] == {"NanoCPUs": int(4.5 * 1e9)} for u in client.updates)
    assert tuner._last == 4.5


async def test_tuner_disabled_without_socket(monkeypatch):
    cfg = Settings(worker_container_names=("w1",))
    monkeypatch.setattr("oxmit.resources.os.path.exists", lambda p: False)
    tuner = WorkerCpuTuner(cfg)
    client = FakeClient()
    tuner._client = None
    monkeypatch.setattr(tuner, "_get_client", lambda: None)
    await tuner.tune(1)   # must not raise
    assert tuner._last is None
