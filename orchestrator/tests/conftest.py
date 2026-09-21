from __future__ import annotations

import os
from pathlib import Path

os.environ["EPOCHDEPLOY_DATABASE_URL"] = "sqlite:///./test_epochdeploy.db"
os.environ["EPOCHDEPLOY_EXECUTOR_MODE"] = "local"
os.environ["EPOCHDEPLOY_UPLOAD_DIR"] = "./test_uploads"
os.environ["EPOCHDEPLOY_JWT_SECRET"] = "test-secret-0123456789abcdef-0123456789"
os.environ["EPOCHDEPLOY_GITLAB_WEBHOOK_TOKEN"] = "test-gitlab-token"
os.environ["EPOCHDEPLOY_DEMO_MODE"] = "true"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as client:
        yield client
    Base.metadata.drop_all(bind=engine)
    import shutil
    shutil.rmtree("test_uploads", ignore_errors=True)


@pytest.fixture
def client(clean_db):
    return clean_db


def login(client, username, password):
    r = client.post("/api/auth/token", json={"username":username, "password":password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def operator(client): return login(client, "operator", "operator-demo")
@pytest.fixture
def approver(client): return login(client, "approver", "approver-demo")
@pytest.fixture
def admin(client): return login(client, "admin", "admin-demo")
