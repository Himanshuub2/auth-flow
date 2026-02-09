from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    VITE_GOOGLE_CLIENT_ID: str
    VITE_GOOGLE_CLIENT_SECRET: str
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    JWT_SECRET: str
    ENV: str
    JWT_ALGORITHM: str
    JWT_EXPIRE_MIN: int
    @property
    def db_url(self):
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()