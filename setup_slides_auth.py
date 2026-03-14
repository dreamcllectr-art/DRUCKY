"""Quick OAuth setup for Google Slides — minimal imports, no heavy deps."""
import os
from pathlib import Path

_root = str(Path(__file__).parent)
CREDS_PATH = os.path.join(_root, "credentials.json")
TOKEN_PATH = os.path.join(_root, "token.json")

SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive.file",
]

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

def main():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print(f"Opening browser for Google OAuth...")
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=8090)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        print(f"Token saved to {TOKEN_PATH}")

    # Quick test
    service = build("slides", "v1", credentials=creds)
    pres = service.presentations().create(body={"title": "Test — Druckenmiller Alpha"}).execute()
    pres_id = pres["presentationId"]
    print(f"Test presentation created: https://docs.google.com/presentation/d/{pres_id}")
    print("Setup complete!")

if __name__ == "__main__":
    main()
