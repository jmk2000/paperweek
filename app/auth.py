"""Google's desktop OAuth flow, with refresh credentials in macOS Keychain."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
from .google_source import SCOPES, CalendarError, GoogleCalendarSource
from .storage import ROOT, data_dir, atomic_write

SERVICE = "Paperweek Calendar Prototype"


class TokenStore:
    def __init__(self, client_id: str):
        self.account = hashlib.sha256(client_id.encode()).hexdigest()[:24]
        self.file = data_dir() / "token.json"
        self.backend = None
        if sys.platform == "darwin":
            try:
                from keyring.backends.macOS import Keyring
                self.backend = Keyring()
            except ImportError:
                raise CalendarError("Keychain support is missing. Run bash setup.sh.") from None
        elif os.environ.get("PAPERWEEK_ALLOW_FILE_TOKEN") != "1":
            raise CalendarError("Google sign-in uses macOS Keychain. See docs/SECURITY.md for Linux development.")

    def load(self) -> str | None:
        try:
            if self.backend:
                return self.backend.get_password(SERVICE, self.account)
            return self.file.read_text() if self.file.exists() else None
        except Exception:
            raise CalendarError("Could not read Keychain. Unlock it and retry.") from None

    def save(self, value: str) -> None:
        try:
            if self.backend:
                self.backend.set_password(SERVICE, self.account, value)
            else:
                atomic_write(self.file, value)
        except Exception:
            raise CalendarError("Could not save credentials securely. Check Keychain permissions.") from None

    def delete(self) -> None:
        if self.backend:
            if self.load() is not None:
                self.backend.delete_password(SERVICE, self.account)
        else:
            self.file.unlink(missing_ok=True)


def client_config(path: Path | None = None) -> dict:
    stored = data_dir() / "credentials.json"
    source = path or (stored if stored.exists() else ROOT / "credentials.json")
    if not source.is_file():
        raise CalendarError("No credentials.json found. Follow docs/GOOGLE_SETUP.md to create a Desktop app client.")
    try:
        data = json.loads(source.read_text())
        installed = data["installed"]
        if not str(installed["client_id"]).endswith(".apps.googleusercontent.com"):
            raise ValueError()
        if installed["token_uri"] != "https://oauth2.googleapis.com/token":
            raise ValueError()
        if installed["auth_uri"] not in ("https://accounts.google.com/o/oauth2/auth",
                                         "https://accounts.google.com/o/oauth2/v2/auth"):
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise CalendarError("Use an unmodified Google Desktop app credentials JSON, not a Web app or service account key.") from None
    if source != stored:
        atomic_write(stored, json.dumps(data))
    return data


def source(interactive: bool = False, credentials_path: Path | None = None) -> GoogleCalendarSource:
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request, AuthorizedSession
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise CalendarError("Google libraries are missing. Run bash setup.sh.") from None
    cfg = client_config(credentials_path)
    store = TokenStore(cfg["installed"]["client_id"])
    creds = None
    if not interactive:
        stored = store.load()
        if stored:
            try:
                creds = Credentials.from_authorized_user_info(json.loads(stored), scopes=SCOPES)
                if not creds.has_scopes(SCOPES):
                    creds = None
                elif not creds.valid and creds.refresh_token:
                    creds.refresh(Request())
            except Exception:
                raise CalendarError("Google sign-in needs renewing. Run ./run.sh connect.") from None
        if creds is None or not creds.valid:
            raise CalendarError("Connect Google first with ./run.sh connect.")
    else:
        print("Opening Google sign-in. Approve both read-only permissions for your Workspace account.", flush=True)
        try:
            flow = InstalledAppFlow.from_client_config(cfg, scopes=SCOPES, autogenerate_code_verifier=True)
            creds = flow.run_local_server(
                host="127.0.0.1", port=0, open_browser=True, timeout_seconds=180,
                access_type="offline", prompt="consent select_account",
                authorization_prompt_message="Complete sign-in in your browser. If it did not open, rerun from your Mac desktop.",
                success_message="Paperweek is connected. You can close this tab and return to Terminal.")
            granted = creds.granted_scopes or creds.scopes or []
            if not set(SCOPES).issubset(set(granted)):
                raise ValueError("Missing scope")
            if not creds.refresh_token:
                raise ValueError("No offline access")
        except Exception:
            raise CalendarError("Sign-in was not completed with both read-only permissions. See docs/GOOGLE_SETUP.md.") from None
    store.save(creds.to_json())
    # requests and google-auth verify HTTPS certificates by default.
    session = AuthorizedSession(creds, refresh_timeout=25)
    return GoogleCalendarSource(session, lambda: store.save(creds.to_json()))


def disconnect() -> None:
    """Forget local credentials. Google-side revocation is a separate, explicit user action."""
    cfg = client_config()
    TokenStore(cfg["installed"]["client_id"]).delete()
    for path in (data_dir() / "cache").glob("*.json"):
        path.unlink()
    for name in ("view.pwv", "export.ppm"):
        (data_dir() / name).unlink(missing_ok=True)
    print("Local token and event cache removed. To revoke the grant too, use your Google Account's third-party connections settings.")
