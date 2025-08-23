from google_auth_oauthlib.flow import InstalledAppFlow
import os

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# client_config = {
#     "installed": {
#         "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
#         "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
#         "auth_uri": "https://accounts.google.com/o/oauth2/auth",
#         "token_uri": "https://oauth2.googleapis.com/token",
#         "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"],
#     }
# }
client_config = {
    "installed": {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
        "project_id": "balanca-ubs",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
        "redirect_uris": ["http://localhost"],
    }
}
flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

# Use open_browser=False para não abrir navegador
creds = flow.run_local_server(port=0, open_browser=False)

print("Seu refresh token é:")
print(creds.refresh_token)
