import gspread
from google.oauth2.service_account import Credentials


CREDENTIALS_FILE = "credentials/google-service-account.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]


credentials = Credentials.from_service_account_file(
    CREDENTIALS_FILE,
    scopes=SCOPES
)

client = gspread.authorize(credentials)


spreadsheet = client.open("Subject Guide Data")

worksheet = spreadsheet.worksheet("departments")

rows = worksheet.get_all_records()


for row in rows:
    print(row)