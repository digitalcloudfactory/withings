import json
import os
from datetime import datetime, timezone
import requests

STATE_FILE = "last_measurement.json"

# 1. Load Secrets from GitHub Environment
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
refresh_token = os.environ.get("REFRESH_TOKEN")
STRIDE_TOKEN = os.environ.get("STRIDE_TOKEN")

STRIDE_API_URL = "https://api.stride.is/v1/athletes/me/metrics"

# 2. Refresh Withings Access Token
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

  # Convert Unix timestamp to ISO 8601 format required by Stride (e.g., 2026-10-22T00:00:00Z)
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

  # Check if any key metric has changed
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

    # Define the metrics to push (adjust type names if Stride expects slightly different labels)
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

    # Send each metric in a separate call
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

    # Save new state locally only if pushes succeeded
    if success:
      with open(STATE_FILE, "w") as f:
        json.dump(latest_entry, f, indent=4)
      print("State file updated successfully.")
  else:
    print("💤 No changes in measurements. Skipping Stride update.")
else:
  print("No measurements found from Withings API.")
print("=" * 40 + "\n")
