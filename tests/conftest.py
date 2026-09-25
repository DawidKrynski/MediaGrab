import os

import pytest
import requests

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def no_external_requests(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Network access is forbidden in ordinary tests")

    monkeypatch.setattr(requests.sessions.Session, "send", denied)


def pytest_addoption(parser):
    parser.addoption(
        "--integration", action="store_true", help="Run real engines against loopback fixtures"
    )
    parser.addoption(
        "--engine-helper",
        help="Run the engines through this portable-build helper executable",
    )


@pytest.fixture(autouse=True)
def portable_engine_helper(request, monkeypatch):
    helper = request.config.getoption("--engine-helper")
    if helper:
        from mediagrab import runtime

        monkeypatch.setattr(runtime, "helper_python", lambda: helper)


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: real CLI, local HTTP fixture only")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(
                    pytest.mark.skip(reason="Use --integration for local real-engine tests")
                )
