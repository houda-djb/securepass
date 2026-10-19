from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
csrf = CSRFProtect()  # SR2: every POST needs a valid CSRF token
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address)  # SR7