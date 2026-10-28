import base64
import time
import requests

BASE_URL = "https://aihorde.net/api/v2"

headers = {
    "apikey": "0000000000",
    "Client-Agent": "pen-art-agent:1.0"
}

prompt = """
A charming everyday scene drawn as handmade pen art,
rough black ink scribbles, imperfect hand-drawn lines,
simple shapes, a few loose crosshatches, white paper,
minimal composition, no text, no watermark.
"""

response = requests.post(
    f"{BASE_URL}/generate/async",
    headers=headers,
    json={
        "prompt": prompt,
        "params": {
            "width": 512,
            "height": 512,
            "steps": 20,
            "n": 1
        }
    },
    timeout=60
)

response.raise_for_status()
job_id = response.json()["id"]

print("Image generation queued:", job_id)

while True:
    status = requests.get(
        f"{BASE_URL}/generate/check/{job_id}",
        headers=headers,
        timeout=30
    )
    status.raise_for_status()

    if status.json().get("done"):
        break

    if status.json().get("faulted"):
        raise RuntimeError("Image generation failed")

    time.sleep(10)

result = requests.get(
    f"{BASE_URL}/generate/status/{job_id}",
    headers=headers,
    timeout=30
)
result.raise_for_status()

image_data = result.json()["generations"][0]["img"]

if image_data.startswith("http"):
    image_response = requests.get(image_data, timeout=60)
    image_response.raise_for_status()
    image_bytes = image_response.content
else:
    if image_data.startswith("data:"):
        image_data = image_data.split(",", 1)[1]

    image_bytes = base64.b64decode(image_data)

with open("test_pen_art.png", "wb") as image_file:
    image_file.write(image_bytes)

print("Saved image as test_pen_art.png")
