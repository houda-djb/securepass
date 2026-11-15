import pytest
from app import create_app
from app.extensions import db
from app.seed import seed_demo_data


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        seed_demo_data(days=30)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()
