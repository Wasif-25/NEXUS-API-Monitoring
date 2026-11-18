
import requests

url = "https://sitdeck.com/api/sitdeck/data-sources"

try:
    response = requests.get(url, timeout=15)

    print("Status Code:", response.status_code)

    response.raise_for_status()

    data = response.json()

    print("\nTotal Data Sources:", data["totalDataSources"])

    print("\nSummary:")
    print(data["summary"])

    print("\nFirst 5 Data Sources:")
    for source in data["dataSources"][:5]:
        print(source)

except Exception as e:
    print("Error:", e)
