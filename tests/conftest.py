import pytest

from app import create_app
from app.seed import seed_demo_data


@pytest.fixture()
def app(tmp_path):
    app = create_app("testing")
    # Tests must never read or write the real instance/ folder (for example a saved scan summary).
    app.instance_path = str(tmp_path)
    with app.app_context():
        seed_demo_data(days=10)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()