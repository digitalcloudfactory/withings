import json
import os
from datetime import datetime, timedelta, timezone
import requests

STATE_FILE = "last_measurement.json"
TOKEN_FILE = "token_state.json"

# 1. Load Secrets & Existing Token State
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
STRIDE_TOKEN = os.environ.get("STRIDE_TOKEN")
STRIDE_API_URL = "https://api.stride.is/v1/athletes/me/metrics"

refresh_token = None
if os.path.exists(TOKEN_FILE):
  try:
    with open(TOKEN_FILE, "r") as f:
      token_data = json.load(f)
      refresh_token = token_data.get("refresh_token")
  except Exception:
    pass

if not refresh_token:
  refresh_token = os.environ.get("REFRESH_TOKEN")

if not refresh_token:
  raise Exception("No valid refresh token found anywhere!")

# 2. Refresh Withings Access Token & New Refresh Token
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

if auth_response.get("status") != 0:
  raise Exception(
      f"Withings authentication failed! Error code: {auth_response}"
  )

access_token = auth_response["body"]["access_token"]
new_refresh_token = auth_response["body"]["refresh_token"]

with open(TOKEN_FILE, "w") as f:
  json.dump({"refresh_token": new_refresh_token}, f, indent=4)

# 3. Fetch Measurements from the Last 2 Days (Ensures we catch today's weigh-in)
two_days_ago = int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp())

meas_response = requests.post(
    "https://wbsapi.withings.net/measure",
    data={
        "action": "getmeas",
        "category": "1",
        "startdate": two_days_ago,  # Uses a time window instead of limit=1
        "access_token": access_token,
    },
).json()

# 4. Parse & Find the Absolute Latest Measurement Group via Python
measuregrps = meas_response.get("body", {}).get("measuregrps", [])
latest_entry = None

if measuregrps:
  # Sort groups by timestamp descending (newest first) to guarantee we get the latest
  measuregrps.sort(key=lambda x: x.get("date", 0), reverse=True)
  grp = measuregrps[0]

  timestamp = grp.get("date")
  iso_timestamp = (
      datetime.fromtimestamp(timestamp, timezone.utc)
      .strftime("%Y-%m-%dT%H:%M:%SZ")
  )

  weight = None
  fat_percentage = None
  muscle_mass = None

  for m in grp.get("measures", []):
    if m["type"] == 1:
      weight = round(m["value"] * (10 ** m["unit"]), 2)
    elif m["type"] == 6:
      fat_percentage = round(m["value"] * (10 ** m["unit"]), 1)
    elif m["type"] == 76:
      muscle_mass = round(m["value"] * (10 ** m["unit"]), 2)

  if weight:
    latest_entry = {
        "timestamp_raw": timestamp,
        "timestamp": iso_timestamp,
        "weight_kg": weight,
        "fat_percentage": fat_percentage,
        "muscle_mass_kg": muscle_mass,
    }

# 5. Load Last Saved Measurement State & Compare
last_data = {}
if os.path.exists(STATE_FILE):
  try:
    with open(STATE_FILE, "r") as f:
      last_data = json.load(f)
  except Exception:
    pass

last_weight = last_data.get("weight_kg")
last_fat = last_data.get("fat_percentage")
last_muscle = last_data.get("muscle_mass_kg")

print("\n" + "=" * 40)
if latest_entry:
  print("Current Reading Found:")
  print(
      f"  Weight: {latest_entry['weight_kg']} kg | Fat: {latest_entry['fat_percentage']}% | Muscle: {latest_entry['muscle_mass_kg']} kg"
  )
  print(f"  Timestamp: {latest_entry['timestamp']}")

  values_changed = (
      latest_entry["weight_kg"] != last_weight
      or latest_entry["fat_percentage"] != last_fat
      or latest_entry["muscle_mass_kg"] != last_muscle
  )

  if values_changed:
    print("✨ Changes detected! Sending updates to Stride...")

    headers = {
        "Authorization": f"Bearer {STRIDE_TOKEN}",
        "Content-Type": "application/json",
    }

    metrics_to_send = []
    if latest_entry["weight_kg"] is not None:
      metrics_to_send.append({
          "type": "WEIGHT",
          "value": latest_entry["weight_kg"],
          "timestamp": latest_entry["timestamp"],
      })
    if latest_entry["fat_percentage"] is not None:
      metrics_to_send.append({
          "type": "FAT_PERCENTAGE",
          "value": latest_entry["fat_percentage"],
          "timestamp": latest_entry["timestamp"],
      })
    if latest_entry["muscle_mass_kg"] is not None:
      metrics_to_send.append({
          "type": "MUSCLE_MASS",
          "value": latest_entry["muscle_mass_kg"],
          "timestamp": latest_entry["timestamp"],
      })

    success = True
    for payload in metrics_to_send:
      try:
        response = requests.post(
            STRIDE_API_URL, headers=headers, json=payload
        )
        print(
            f"Sent {payload['type']} ({payload['value']}) -> Status:"
            f" {response.status_code}"
        )
        if response.status_code not in [200, 201]:
          print(f"Response body: {response.text}")
          success = False
      except Exception as e:
        print(f"Failed to send {payload['type']}: {e}")
        success = False

    if success:
      with open(STATE_FILE, "w") as f:
        json.dump(latest_entry, f, indent=4)
      print("Measurement state file updated successfully.")
  else:
    print("💤 No changes in measurements compared to last saved state.")
else:
  print("No measurements found from Withings API within the time window.")
print("=" * 40 + "\n")
