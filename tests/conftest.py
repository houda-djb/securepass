import pytest

from app import create_app
from app.seed import seed_demo_data


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        seed_demo_data(days=10)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()