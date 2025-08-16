# config.py
import os

class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # good for noisy networks / restarts
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }
    REDIS_URL = os.getenv("REDIS_URL")  # for Socket.IO, optional

class DevConfig(BaseConfig):
    # keep sqlite for dev if you like
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "SQLALCHEMY_DATABASE_URI",
        "sqlite:///instance/warehouse.db"
    )

class ProdConfig(BaseConfig):
    SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")  # must be set
