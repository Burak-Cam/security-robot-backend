from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()

# 🔓 CORS ayarı (frontend erişimi için)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 📁 Klasör tanımları
IMAGE_FOLDER = "/home/mergen/Desktop/db/Images"
LOG_FOLDER = "/home/mergen/Desktop/db/Logs"

@app.get("/")
def root():
    return {"message": "FastAPI is running on Pi4"}

# 🖼️ /images
@app.get("/images")
def list_image_files():
    try:
        files = sorted(
            [{"filename": f, "url": f"/image/{f}"} for f in os.listdir(IMAGE_FOLDER) if f.lower().endswith(".jpg")],
            key=lambda x: x["filename"],
            reverse=True
        )
        return files
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image folder error: {e}")

# 🖼️ /Images (alias)
@app.get("/Images")
def get_images_alias():
    return list_image_files()

# 🖼️ /image/{filename}
@app.get("/image/{filename}")
def serve_image(filename: str):
    path = os.path.join(IMAGE_FOLDER, filename)
    if os.path.exists(path):
        return FileResponse(path, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="Image not found")

# 📄 /logs
@app.get("/logs")
def list_log_files():
    try:
        files = sorted(
            [{"filename": f, "url": f"/log/{f}"} for f in os.listdir(LOG_FOLDER) if f.lower().endswith(".json")],
            key=lambda x: x["filename"],
            reverse=True
        )
        return files
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Log folder error: {e}")

# 📄 /Logs (alias)
@app.get("/Logs")
def get_logs_alias():
    return list_log_files()

# 📄 /log/{filename}
@app.get("/log/{filename}")
def serve_log(filename: str):
    path = os.path.join(LOG_FOLDER, filename)
    if os.path.exists(path):
        return FileResponse(path, media_type="application/json")
    raise HTTPException(status_code=404, detail="Log file not found")
