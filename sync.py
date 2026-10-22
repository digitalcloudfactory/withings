import json
import os
from datetime import datetime
import requests

STATE_FILE = "last_measurement.json"

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

if auth_response.get("status") != 0:
  raise Exception(
      f"Withings authentication failed! Error code: {auth_response}"
  )

access_token = auth_response["body"]["access_token"]

# 3. Fetch ONLY the Latest Measurement (limit=1)
meas_response = requests.post(
    "https://wbsapi.withings.net/measure",
    data={
        "action": "getmeas",
        "category": "1",
        "limit": "1",
        "access_token": access_token,
    },
).json()

# 4. Parse & Extract Latest Metrics
measuregrps = meas_response.get("body", {}).get("measuregrps", [])
latest_entry = None

if measuregrps:
  grp = measuregrps[0]
  timestamp = grp.get("date")
  readable_date = datetime.utcfromtimestamp(timestamp).strftime(
      "%Y-%m-%d %H:%M:%S"
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
        "timestamp": timestamp,
        "date": readable_date,
        "weight_kg": weight,
        "fat_percentage": fat_percentage,
        "muscle_mass_kg": muscle_mass,
    }

# 5. Load Last Saved State
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
  print("Current Reading:")
  print(
      f"  Weight: {latest_entry['weight_kg']} kg | Fat: {latest_entry['fat_percentage']}% | Muscle: {latest_entry['muscle_mass_kg']} kg"
  )
  print("Last Saved Reading:")
  print(
      f"  Weight: {last_weight} kg | Fat: {last_fat}% | Muscle: {last_muscle} kg"
  )

  # Check if any key metric has changed
  values_changed = (
      latest_entry["weight_kg"] != last_weight
      or latest_entry["fat_percentage"] != last_fat
      or latest_entry["muscle_mass_kg"] != last_muscle
  )

  if values_changed:
    print("✨ Change detected in values! Triggering update...")

    # Send to target URL if configured
    if TARGET_URL:
      try:
        response = requests.post(TARGET_URL, json=latest_entry)
        print(f"Target URL Response Status: {response.status_code}")
      except Exception as e:
        print(f"Failed to send to target URL: {e}")
    else:
      print("No TARGET_API_URL set, skipping external push.")

    # Save new state locally so git can commit it
    with open(STATE_FILE, "w") as f:
      json.dump(latest_entry, f, indent=4)
    print("State file updated successfully.")

  else:
    print("💤 No changes in weight or body composition. Skipping update.")
else:
  print("No measurements found from Withings API.")
print("=" * 40 + "\n")
