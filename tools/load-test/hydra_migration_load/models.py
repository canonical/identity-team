from dataclasses import dataclass
from typing import List


@dataclass
class IdentityRecord:
    id: str
    email: str
    password: str
    totp_secret: str


@dataclass
class ClientRecord:
    client_id: str
    client_secret: str
    redirect_uri: str


@dataclass
class SetupData:
    identities: List[IdentityRecord]
    clients: List[ClientRecord]
