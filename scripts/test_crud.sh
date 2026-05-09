#!/bin/bash
# Full CRUD test for all endpoints
set -e

BASE="http://localhost:8100/api/v1"
TOKEN=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@aiparking.com","password":"Admin@123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

AUTH="Authorization: Bearer $TOKEN"
CT="Content-Type: application/json"

pass=0
fail=0

test_endpoint() {
  local method=$1 url=$2 data=$3 expected_code=$4 label=$5

  if [ -n "$data" ]; then
    response=$(curl -s -w "\n%{http_code}" -X "$method" "$url" -H "$AUTH" -H "$CT" -d "$data")
  else
    response=$(curl -s -w "\n%{http_code}" -X "$method" "$url" -H "$AUTH")
  fi

  code=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  if [ "$code" = "$expected_code" ]; then
    echo "PASS [$code] $label"
    ((pass++))
  else
    echo "FAIL [$code != $expected_code] $label"
    echo "  Response: $body"
    ((fail++))
  fi

  # Return body for chaining
  echo "$body" > /tmp/crud_last_response.json
}

extract_id() {
  python3 -c "import sys,json; print(json.load(open('/tmp/crud_last_response.json'))['id'])"
}

echo "========================================="
echo "  AI Parking - Full CRUD Test Suite"
echo "========================================="
echo ""

# --- AUTH ---
echo "--- Auth ---"
test_endpoint POST "$BASE/auth/login" '{"email":"admin@aiparking.com","password":"Admin@123"}' 200 "Login"
test_endpoint POST "$BASE/auth/login" '{"email":"admin@aiparking.com","password":"wrong"}' 401 "Login bad password"

# --- USERS ---
echo ""
echo "--- Users ---"
test_endpoint GET "$BASE/users/me" "" 200 "Get current user"
test_endpoint GET "$BASE/users" "" 200 "List users"

# --- STATES ---
echo ""
echo "--- States ---"

# Delete existing MH state if exists from previous test
curl -s "$BASE/states?page_size=100" -H "$AUTH" | python3 -c "
import sys,json
data = json.load(sys.stdin)
for s in data.get('items',[]):
    if s['code'] == 'MH':
        print(s['id'])
" > /tmp/existing_mh.txt
EXISTING_MH=$(cat /tmp/existing_mh.txt)
if [ -n "$EXISTING_MH" ]; then
  curl -s -X DELETE "$BASE/states/$EXISTING_MH" -H "$AUTH" > /dev/null 2>&1
fi

test_endpoint POST "$BASE/states" '{"name":"Maharashtra","code":"MH","country":"India"}' 201 "Create state"
STATE_ID=$(extract_id)
test_endpoint GET "$BASE/states/$STATE_ID" "" 200 "Get state"
test_endpoint GET "$BASE/states" "" 200 "List states"
test_endpoint PATCH "$BASE/states/$STATE_ID" '{"name":"Maharashtra Updated"}' 200 "Update state"
# Don't delete yet, need it for cities

# --- CITIES ---
echo ""
echo "--- Cities ---"
test_endpoint POST "$BASE/cities" "{\"name\":\"Pune\",\"state_id\":\"$STATE_ID\"}" 201 "Create city"
CITY_ID=$(extract_id)
test_endpoint GET "$BASE/cities/$CITY_ID" "" 200 "Get city"
test_endpoint GET "$BASE/cities?state_id=$STATE_ID" "" 200 "List cities by state"
test_endpoint PATCH "$BASE/cities/$CITY_ID" '{"name":"Pune Updated"}' 200 "Update city"

# --- AREAS ---
echo ""
echo "--- Areas ---"
test_endpoint POST "$BASE/areas" "{\"name\":\"Kothrud\",\"city_id\":\"$CITY_ID\"}" 201 "Create area"
AREA_ID=$(extract_id)
test_endpoint GET "$BASE/areas/$AREA_ID" "" 200 "Get area"
test_endpoint GET "$BASE/areas?city_id=$CITY_ID" "" 200 "List areas by city"
test_endpoint PATCH "$BASE/areas/$AREA_ID" '{"name":"Kothrud Updated"}' 200 "Update area"

# --- LOCATIONS ---
echo ""
echo "--- Locations ---"
test_endpoint POST "$BASE/locations" "{\"name\":\"Phoenix Mall Parking\",\"area_id\":\"$AREA_ID\",\"address\":\"Phoenix Mall, Nagar Road\",\"latitude\":18.5204,\"longitude\":73.8567,\"location_type\":\"MALL\",\"total_capacity\":480}" 201 "Create location"
LOCATION_ID=$(extract_id)
test_endpoint GET "$BASE/locations/$LOCATION_ID" "" 200 "Get location"
test_endpoint GET "$BASE/locations?area_id=$AREA_ID" "" 200 "List locations by area"
test_endpoint PATCH "$BASE/locations/$LOCATION_ID" '{"name":"Phoenix Mall Parking Updated"}' 200 "Update location"

# --- FLOORS ---
echo ""
echo "--- Floors ---"
test_endpoint POST "$BASE/floors" "{\"location_id\":\"$LOCATION_ID\",\"label\":\"B1\",\"level_number\":-1,\"capacity\":80}" 201 "Create floor"
FLOOR_ID=$(extract_id)
test_endpoint GET "$BASE/floors/$FLOOR_ID" "" 200 "Get floor"
test_endpoint GET "$BASE/floors?location_id=$LOCATION_ID" "" 200 "List floors by location"
test_endpoint PATCH "$BASE/floors/$FLOOR_ID" '{"label":"Basement 1"}' 200 "Update floor"

# --- ZONES ---
echo ""
echo "--- Zones ---"
test_endpoint POST "$BASE/zones" "{\"name\":\"Zone A\",\"floor_id\":\"$FLOOR_ID\",\"capacity\":40}" 201 "Create zone"
ZONE_ID=$(extract_id)
test_endpoint GET "$BASE/zones/$ZONE_ID" "" 200 "Get zone"
test_endpoint GET "$BASE/zones?floor_id=$FLOOR_ID" "" 200 "List zones by floor"
test_endpoint PATCH "$BASE/zones/$ZONE_ID" '{"name":"Zone A Updated"}' 200 "Update zone"

# --- PARKING SLOTS ---
echo ""
echo "--- Parking Slots ---"
test_endpoint POST "$BASE/parking-slots" "{\"label\":\"A-01\",\"zone_id\":\"$ZONE_ID\",\"state\":\"EMPTY\"}" 201 "Create slot"
SLOT_ID=$(extract_id)
test_endpoint GET "$BASE/parking-slots/$SLOT_ID" "" 200 "Get slot"
test_endpoint GET "$BASE/parking-slots?zone_id=$ZONE_ID" "" 200 "List slots by zone"
test_endpoint PATCH "$BASE/parking-slots/$SLOT_ID" '{"state":"VEHICLE"}' 200 "Update slot to VEHICLE"
test_endpoint PATCH "$BASE/parking-slots/$SLOT_ID" '{"state":"OBSTRUCTED"}' 200 "Update slot to OBSTRUCTED"
test_endpoint GET "$BASE/parking-slots/zone/$ZONE_ID/stats" "" 200 "Get zone occupancy stats"

# --- DEVICES ---
echo ""
echo "--- Devices ---"
test_endpoint POST "$BASE/devices" "{\"device_id\":\"RPi-001\",\"location_id\":\"$LOCATION_ID\",\"zone_id\":\"$ZONE_ID\",\"ip_address\":\"192.168.1.100\",\"docker_image_version\":\"v2.4.1\"}" 201 "Create device"
DEVICE_UUID=$(extract_id)
test_endpoint GET "$BASE/devices/$DEVICE_UUID" "" 200 "Get device"
test_endpoint GET "$BASE/devices?location_id=$LOCATION_ID" "" 200 "List devices by location"
test_endpoint PATCH "$BASE/devices/$DEVICE_UUID" '{"status":"ONLINE","ip_address":"192.168.1.101"}' 200 "Update device"

# --- DELETE (reverse order) ---
echo ""
echo "--- Deletes (reverse order) ---"
test_endpoint DELETE "$BASE/devices/$DEVICE_UUID" "" 200 "Delete device"
test_endpoint DELETE "$BASE/parking-slots/$SLOT_ID" "" 200 "Delete slot"
test_endpoint DELETE "$BASE/zones/$ZONE_ID" "" 200 "Delete zone"
test_endpoint DELETE "$BASE/floors/$FLOOR_ID" "" 200 "Delete floor"
test_endpoint DELETE "$BASE/locations/$LOCATION_ID" "" 200 "Delete location"
test_endpoint DELETE "$BASE/areas/$AREA_ID" "" 200 "Delete area"
test_endpoint DELETE "$BASE/cities/$CITY_ID" "" 200 "Delete city"
test_endpoint DELETE "$BASE/states/$STATE_ID" "" 200 "Delete state"

# --- 404 Tests ---
echo ""
echo "--- 404 Tests ---"
test_endpoint GET "$BASE/states/00000000-0000-0000-0000-000000000000" "" 404 "Get non-existent state"
test_endpoint GET "$BASE/devices/00000000-0000-0000-0000-000000000000" "" 404 "Get non-existent device"

# --- SUMMARY ---
echo ""
echo "========================================="
echo "  Results: $pass passed, $fail failed"
echo "========================================="

# Cleanup
rm -f /tmp/crud_last_response.json /tmp/existing_mh.txt

exit $fail
