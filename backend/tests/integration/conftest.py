import pytest

from .rig import AppRig, EmbeddedBroker, SubprocessApp


@pytest.fixture
def broker():
    b = EmbeddedBroker().start()
    try:
        yield b
    finally:
        b.stop()


@pytest.fixture
def make_app(tmp_path, broker):
    """Factory for an `AppRig`; entering and cleanup are the test's / this fixture's job."""
    rigs = []

    def factory(**kw):
        rig = AppRig(tmp_path, broker, **kw)
        rigs.append(rig)
        return rig

    yield factory


@pytest.fixture
def subprocess_app(tmp_path, broker):
    apps = []

    def factory(**extra):
        app = SubprocessApp(tmp_path, broker.port, **extra)
        apps.append(app)
        return app

    yield factory
    for app in apps:
        app.cleanup()
