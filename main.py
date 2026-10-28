
import os
import time
import base64
import random
import requests
import cloudinary
import cloudinary.uploader

from flask import Flask, request, jsonify
from io import BytesIO
from PIL import Image

app = Flask(__name__)

# Read secrets from environment variables
AI_HORDE_KEY = os.getenv("AI_HORDE_KEY", "0000000000")
CLOUD_NAME = os.environ["CLOUDINARY_CLOUD_NAME"]
CLOUD_KEY = os.environ["CLOUDINARY_API_KEY"]
CLOUD_SECRET = os.environ["CLOUDINARY_API_SECRET"]

IG_USER_ID = os.environ["IG_USER_ID"]
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
JOB_SECRET = os.environ["JOB_SECRET"]

# Set this to a currently supported Graph API version
GRAPH_VERSION = os.environ["GRAPH_VERSION"]

cloudinary.config(
    cloud_name=CLOUD_NAME,
    api_key=CLOUD_KEY,
    api_secret=CLOUD_SECRET
)

subjects = [
    "a cat sitting beside a cup of tea",
    "a person walking with a dog in the rain",
    "a tiny house under a giant tree",
    "two friends sharing an umbrella",
    "a sleepy cat on a windowsill",
    "a person reading beside a window",
    "a vase of wildflowers on a table",
    "a little bird sitting on a branch",
    "a person looking at the moon",
    "a bicycle parked beside a flower shop"
]

def generate_image():
    subject = random.choice(subjects)

    prompt = (
        f"{subject}, handmade pen art, imperfect black ink "
        "lines, loose scribbles, simple hand-drawn shapes, "
        "minimal crosshatching, white background, charming "
        "sketchbook aesthetic, no words, no watermark"
    )

    base_url = "https://aihorde.net/api/v2"

    headers = {
        "apikey": AI_HORDE_KEY,
        "Client-Agent": "pen-art-agent:1.0"
    }

    response = requests.post(
        f"{base_url}/generate/async",
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

    # Wait up to 15 minutes for a result
    for attempt in range(90):
        time.sleep(10)

        check = requests.get(
            f"{base_url}/generate/check/{job_id}",
            headers=headers,
            timeout=30
        )
        check.raise_for_status()
        status = check.json()

        if status.get("faulted"):
            raise RuntimeError("AI image generation failed")

        if status.get("done"):
            break
    else:
        raise TimeoutError("AI image generation took too long")

    result = requests.get(
        f"{base_url}/generate/status/{job_id}",
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

    # Convert to JPEG for Instagram publishing
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    output = BytesIO()
    image.save(output, format="JPEG", quality=90)

    return subject, output.getvalue()


def upload_image(image_bytes):
    data_uri = (
        "data:image/jpeg;base64,"
        + base64.b64encode(image_bytes).decode("utf-8")
    )

    result = cloudinary.uploader.upload(
        data_uri,
        folder="pen_art_agent",
        resource_type="image"
    )

    return result["secure_url"]


def publish_to_instagram(image_url, subject):
    base_url = (
        f"https://graph.instagram.com/{GRAPH_VERSION}"
        f"/{IG_USER_ID}"
    )

    # Step 1: Create the media container
    container = requests.post(
        f"{base_url}/media",
        data={
            "image_url": image_url,
            "caption": (
                f"Today's little pen-art moment: {subject} ✍️\n\n"
                "#PenArt #HandDrawn #ScribbleArt "
                "#DailyArt #InkSketch"
            ),
            "access_token": IG_ACCESS_TOKEN
        },
        timeout=60
    )
    container.raise_for_status()
    container_id = container.json()["id"]

    # Step 2: Wait for the container to be ready
    for attempt in range(12):
        time.sleep(5)

        check = requests.get(
            f"https://graph.instagram.com/{GRAPH_VERSION}/"
            f"{container_id}",
            params={
                "fields": "status_code",
                "access_token": IG_ACCESS_TOKEN
            },
            timeout=30
        )
        check.raise_for_status()
        state = check.json().get("status_code")

        if state == "FINISHED":
            break

        if state in ("ERROR", "EXPIRED"):
            raise RuntimeError(
                f"Instagram container status: {state}"
            )
    else:
        raise TimeoutError("Instagram media container not ready")

    # Step 3: Publish the container
    published = requests.post(
        f"{base_url}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": IG_ACCESS_TOKEN
        },
        timeout=60
    )
    published.raise_for_status()

    return published.json()["id"]


@app.route("/run", methods=["POST"])
def run_daily_job():
    # Protect the endpoint from unauthorized requests
    if request.headers.get("X-Job-Secret") != JOB_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        subject, image_bytes = generate_image()
        image_url = upload_image(image_bytes)
        post_id = publish_to_instagram(image_url, subject)

        return jsonify({
            "status": "success",
            "subject": subject,
            "instagram_post_id": post_id
        }), 200

    except Exception:
        app.logger.exception("Daily publishing job failed")
        return jsonify({
            "status": "failed",
            "message": "Check cloud logs for the error."
        }), 500


@app.route("/", methods=["GET"])
def home():
    return "Pen-art automation service is running."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(
        os.getenv("PORT", "8080")
    ))
