from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from datetime import datetime
import os
import time
import requests
import threading

# === FastAPI Settings ===
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Database Settings ===
engine = create_engine("postgresql://db_admin:iku1234@localhost:5432/robot_db")

# === Folder and AI API Settings ===
IMAGE_FOLDER = "/home/mergen/Desktop/db/Images"
AI_ENDPOINT = "http://10.146.40.152:8600/upload-image"  # AI PC FastAPI endpoint

sent_files = set()

# === Thread: Send new images to AI ===
def send_images_to_ai():
    print("[🚀] Image sender started")
    while True:
        try:
            images = sorted(f for f in os.listdir(IMAGE_FOLDER) if f.endswith(".jpg"))
            for img_file in images:
                if img_file in sent_files:
                    continue

                img_path = os.path.join(IMAGE_FOLDER, img_file)
                # Check if image has been inserted into DB and get its ID
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT imageid FROM Image_Data WHERE ImagePath = :p"), {"p": img_path}).fetchone()
                if result is None:
                    # Image not yet in database; try again later
                    continue
                imageid = result[0]

                # Send image file (with imageid) to AI endpoint
                with open(img_path, "rb") as f:
                    files = {"file": (img_file, f, "image/jpeg")}
                    data = {"imageid": str(imageid)}
                    res = requests.post(AI_ENDPOINT, files=files, data=data, timeout=30)

                if res.status_code == 200:
                    print(f"[✓] Sent → {img_file} (ID={imageid})")
                    sent_files.add(img_file)
                else:
                    print(f"[!] Failed to send: {img_file} → Status {res.status_code}")
            time.sleep(2)
        except Exception as e:
            print(f"[X] Sending error: {e}")
            time.sleep(3)

# === Endpoint: Receive AI log (optional use) ===
@app.post("/receive-ai-log")
async def receive_ai_log(request: Request):
    try:
        data = await request.json()
        logs = data.get("logs", [])
        with engine.connect() as conn:
            for entry in logs:
                conn.execute(text("""
                    INSERT INTO ai_results (anomalystatus, description, objectid, robotid, date)
                    VALUES (:status, :desc, :objid, :robotid, :dt)
                """), {
                    "status": entry.get("anomalystatus"),
                    "desc": entry.get("description"),
                    "objid": entry.get("objectid", 0),
                    "robotid": entry.get("robotid", 2),
                    "dt": entry.get("date", datetime.now().isoformat())
                })
        print(f"[AI LOG ✓] {len(logs)} records inserted")
        return {"status": f"{len(logs)} log entries processed"}
    except Exception as e:
        print(f"[!] Log reception error: {e}")
        return {"error": str(e)}

# === Main: start sender thread and API server ===
if __name__ == "__main__":
    import uvicorn
    threading.Thread(target=send_images_to_ai, daemon=True).start()
    uvicorn.run("full_api:app", host="0.0.0.0", port=8500)
