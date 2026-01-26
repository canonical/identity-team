from dataclasses import dataclass


@dataclass
class Endpoints:
    kratos_admin: str = "http://10.152.183.178:4434"
    kratos_public: str = "http://10.152.183.178:4433"
    hydra_admin: str = "http://10.152.183.55:4445/admin"
    hydra_public: str = "https://10.64.140.43"
    login_ui: str = "https://10.64.140.43/ui/login"
    login_ui_base_url: str = "https://10.64.140.43"


DEFAULT_PASSWORD = "Password123!"
DEFAULT_REDIRECT_URI = "https://10.64.140.43/callback"
