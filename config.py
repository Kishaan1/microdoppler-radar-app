"""
config.py
---------
Centralized configuration for the Micro-Doppler Radar Target Classification
web application. All values are read from environment variables so the same
codebase can run locally, in Docker, or on a cloud host (Render, Heroku, AWS
Elastic Beanstalk / ECS) without code changes.
"""

import os
from datetime import timedelta


def _bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    # --- Flask core -------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    DEBUG = _bool(os.environ.get("FLASK_DEBUG"), default=False)
    ENV = os.environ.get("FLASK_ENV", "production")

    # --- Database (PostgreSQL / SQLite via SQLAlchemy) ----------------------
    _raw_db_url = os.environ.get("DATABASE_URL")
    if not _raw_db_url:
        _raw_db_url = "sqlite:///radar.db"
    elif _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = _raw_db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # --- SocketIO -----------------------------------------------------------
    SOCKETIO_MESSAGE_QUEUE = os.environ.get("REDIS_URL")  # optional, for multi-worker deployments
    SOCKETIO_ASYNC_MODE = os.environ.get("SOCKETIO_ASYNC_MODE", "threading")

    # --- Edge node / radar simulation ---------------------------------------
    RADAR_STREAM_HZ = float(os.environ.get("RADAR_STREAM_HZ", 10))  # 10 Hz live feed
    RADAR_STREAM_INTERVAL = 1.0 / RADAR_STREAM_HZ
    CLASSIFICATION_PERSIST_EVERY_N = int(os.environ.get("CLASSIFICATION_PERSIST_EVERY_N", 10))

    # --- Misc -----------------------------------------------------------
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)


class DevelopmentConfig(Config):
    DEBUG = True
    ENV = "development"


class ProductionConfig(Config):
    DEBUG = False
    ENV = "production"


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config():
    return config_by_name.get(os.environ.get("FLASK_ENV", "production"), ProductionConfig)
