import requests

# Test location: Ludhiana, Punjab
latitude = 30.9010
longitude = 75.8573

url = "https://archive-api.open-meteo.com/v1/archive"

params = {
    "latitude": latitude,
    "longitude": longitude,

    # Small date range for testing
    "start_date": "2024-01-01",
    "end_date": "2024-01-07",

    # Weather variables we potentially need
    "daily": [
        "temperature_2m_mean",
        "temperature_2m_max",
        "temperature_2m_min",
        "rain_sum",
        "relative_humidity_2m_mean",
        "wind_speed_10m_mean",
        "et0_fao_evapotranspiration"
    ],

    "timezone": "Asia/Kolkata"
}

print("Testing Open-Meteo Historical Weather API...")
print("Location:", latitude, longitude)
print("Date:", params["start_date"], "to", params["end_date"])

try:
    response = requests.get(
        url,
        params=params,
        timeout=(10, 60)
    )

    print("\nStatus:", response.status_code)

    if response.status_code == 200:

        data = response.json()

        print("\n✅ API WORKING!")
        print("\nReturned location:")
        print("Latitude:", data.get("latitude"))
        print("Longitude:", data.get("longitude"))

        print("\nAvailable daily variables:")
        print(data["daily"].keys())

        print("\nFirst few records:")

        dates = data["daily"]["time"]

        for i in range(min(5, len(dates))):
            print(
                dates[i],
                "| Temp:",
                data["daily"]["temperature_2m_mean"][i],
                "| Rain:",
                data["daily"]["rain_sum"][i],
                "| Humidity:",
                data["daily"]["relative_humidity_2m_mean"][i]
            )

    else:
        print("\n❌ API request failed")
        print(response.text[:3000])

except requests.exceptions.Timeout:
    print("\n❌ Request timed out")

except requests.exceptions.RequestException as e:
    print("\n❌ Request error:")
    print(e)