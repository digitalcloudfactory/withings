import os
import requests
from datetime import datetime, timedelta

# 1. Load Secrets from GitHub Environment
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
refresh_token = os.environ.get("REFRESH_TOKEN")
TARGET_URL = os.environ.get("TARGET_API_URL")

# 2. Refresh Access Token
auth_response = requests.post(
    "https://wbsapi.withings.net/v2/oauth2",
    data={
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
    },
).json()

access_token = auth_response["body"]["access_token"]
# Note: You can also grab the rotated new refresh_token here if you want to auto-update it!

# 3. Fetch Measurements (Last 7 Days)
seven_days_ago = int((datetime.utcnow() - timedelta(days=7)).timestamp())

meas_response = requests.post(
    "https://wbsapi.withings.net/measure",
    data={
        "action": "getmeas",
        "category": "1",
        "startdate": seven_days_ago,
        "access_token": access_token,
    },
).json()

# 4. Parse & Extract Metrics (Weight & Fat Mass)
measuregrps = meas_response.get("body", {}).get("measuregrps", [])
parsed_data = []

for grp in measuregrps:
  timestamp = grp.get("date")
  weight = None
  fat_mass = None

  for m in grp.get("measures", []):
    if m["type"] == 1:  # Weight
      weight = m["value"] * (10 ** m["unit"])
    elif m["type"] == 8:  # Fat Mass
      fat_mass = m["value"] * (10 ** m["unit"])

  if weight:
    parsed_data.append(
        {"date": timestamp, "weight_kg": weight, "fat_mass_kg": fat_mass}
    )

# 5. Send to your External Site / API
if parsed_data:
  # Send latest or all collected records to your destination site
  requests.post(TARGET_URL, json=parsed_data[0])
  print(f"Successfully synced: {parsed_data[0]}")
else:
  print("No new measurements found for this week.")
