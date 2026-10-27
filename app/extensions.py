from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()  # database changes are recorded in the migrations/ folder
csrf = CSRFProtect()  # SR2: every POST needs a valid CSRF token
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address)  # SR7