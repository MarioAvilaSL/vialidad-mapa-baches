from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    # BD propia (PostgreSQL + PostGIS)
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/baches_mapa"

    # BD del proyecto original (solo lectura). Vacía = no configurada.
    origen_database_url: str = ""
    origen_storage_dir: str = ""
    origen_nombre: str = "vialidad-yolo"   # nombre de la fuente en la BD propia (identifica de dónde viene cada bache)

    storage_dir: Path = Path("storage")
    # Orígenes web autorizados. Los de localhost sin puerto son los de la app Android (Capacitor).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,https://localhost,http://localhost,capacitor://localhost"
    # Clave de acceso opcional para las operaciones que modifican datos (importar, cambiar ajustes). Vacía = sin clave.
    api_token: str = ""
    timezone: str = "America/Guayaquil"

    # Motor de rutas (GraphHopper, Fase 5B). Vacío = sin motor de rutas (el resto de la aplicación funciona igual).
    routing_url: str = "http://localhost:8989"
    routing_profile: str = "car"
    routing_timeout_s: float = 20.0

    def storage_path(self) -> Path:
        return self.storage_dir if self.storage_dir.is_absolute() else BASE_DIR / self.storage_dir

    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
