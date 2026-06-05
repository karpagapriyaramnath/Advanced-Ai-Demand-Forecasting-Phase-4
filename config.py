from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    product_name: str = "Advanced AI Demand Forecasting Enhancement API"
    version: str = "1.0.0"
    database_url: str = "sqlite:///./enhancement_forecasting.db"
    jwt_secret: str = "replace-this-priya-secret"
    jwt_algorithm: str = "HS256"
    token_minutes: int = 1440
    cors_origins: list[str] = [
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:5274",
        "http://localhost:5274",
        "http://127.0.0.1:5275",
        "http://localhost:5275",
    ]


settings = AppSettings()
