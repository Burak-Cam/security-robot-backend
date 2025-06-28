#!/usr/bin/python3
import os
import psycopg2
import time
import json
import csv
from datetime import datetime

# PostgreSQL connection
conn = psycopg2.connect(
    dbname="robot_db",
    user="db_admin",
    password="iku1234",
    host="localhost",
    port="5432"
)
cur = conn.cursor()

# Directories
frames_dir = "/home/mergen/Desktop/db/Images"
logs_dir = "/home/mergen/Desktop/db/Logs"
ai_log_path = os.path.join(logs_dir, "ai_log.txt")
log_file = os.path.join(logs_dir, "log.txt")
image_info_file = os.path.join(logs_dir, "image_info.json")

# Create directories if they don't exist
os.makedirs(frames_dir, exist_ok=True)
os.makedirs(logs_dir, exist_ok=True)

processed_files = set()

print("📱 Listening for incoming files...")

while True:
    try:
        timestamp = datetime.now()

        # === 1. IMAGES ===
        images = sorted([f for f in os.listdir(frames_dir) if f.endswith(".jpg")])
        for image_file in images:
            if image_file in processed_files:
                continue

            image_path = os.path.join(frames_dir, image_file)
            cur.execute("""
                INSERT INTO Image_Data (ImageTime, ImagePath, Robot_LocationID, RobotID, ObjectID)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING imageid
            """, (timestamp, image_path, 2, 2, 2))
            imageid = cur.fetchone()[0]
            conn.commit()

            info = {"imageid": imageid, "filename": image_file}
            with open(image_info_file, "w") as jf:
                json.dump(info, jf)
            print(f"[INFO] image_info.json created for {image_file} (ID={imageid})")

            log_entry = f"[{timestamp}] Image saved: {image_file} (ID={imageid})\n"
            with open(log_file, "a") as logf:
                logf.write(log_entry)
            cur.execute("""
                INSERT INTO Logs (LogTime, Action, UserID, LogFilePath)
                VALUES (%s, %s, %s, %s)
            """, (timestamp, f"Image {image_file} inserted with ID={imageid}", 2, log_file))
            conn.commit()

            print(f"[IMG ✓] {image_file} processed with ID={imageid}")
            processed_files.add(image_file)

        # === 2. JSON LOGS ===
        json_logs = sorted([f for f in os.listdir(logs_dir) if f.endswith(".json") and f.lower() != "image_info.json"])
        for json_file in json_logs:
            if json_file in processed_files:
                continue

            json_path = os.path.join(logs_dir, json_file)
            json_file_lower = json_file.lower()
            with open(json_path, "r") as jf:
                if json_file_lower.startswith("arduino_"):
                    try:
                        data_raw = json.load(jf)
                        data_list = [data_raw] if isinstance(data_raw, dict) else data_raw
                        for data in data_list:
                            cur.execute("""
                                INSERT INTO arduino_logs (timestamp, gyrox, gyroy, gyroz, neckservo, headservo,
                                                           frontdistance, leftdistance, rightdistance, motorstate)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (
                                data.get("Timestamp"),
                                data.get("Gyro", {}).get("X"),
                                data.get("Gyro", {}).get("Y"),
                                data.get("Gyro", {}).get("Z"),
                                data.get("ServoAngles", {}).get("Neck"),
                                data.get("ServoAngles", {}).get("Head"),
                                data.get("Distances", {}).get("Front"),
                                data.get("Distances", {}).get("Left"),
                                data.get("Distances", {}).get("Right"),
                                data.get("MotorState")
                            ))
                        conn.commit()
                        action = f"Arduino data parsed and inserted: {json_file}"
                    except Exception as e:
                        action = f"[ERROR] Failed to parse Arduino JSON ({json_file}): {e}"
                        print(action)
                elif json_file_lower in ("pi5_latest.json", "pi5_status.json"):
                    try:
                        data = json.load(jf)
                        cur.execute("""
                            INSERT INTO pi5_stats (timestamp, cpu, ram, cpu_temp, gpu_temp, upload_speed, download_speed)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            data.get("Timestamp"),
                            data.get("CPU"),
                            data.get("RAM"),
                            data.get("CPU Temp"),
                            data.get("GPU Temp"),
                            data.get("Upload (KB/s)"),
                            data.get("Download (KB/s)")
                        ))
                        conn.commit()
                        action = "Pi5 system stats parsed and inserted"
                    except Exception as e:
                        action = f"[ERROR] Failed to parse Pi5 stats ({json_file}): {e}"
                        print(action)
                else:
                    action = f"Unknown JSON file ignored: {json_file}"

            log_entry = f"[{timestamp}] {action}\n"
            with open(log_file, "a") as logf:
                logf.write(log_entry)
            cur.execute("""
                INSERT INTO Logs (LogTime, Action, UserID, LogFilePath)
                VALUES (%s, %s, %s, %s)
            """, (timestamp, action, 2, log_file))
            conn.commit()

            print(f"[JSON ✓] {json_file} processed")
            processed_files.add(json_file)

        # === 3. AI LOG (ONLY LAST LINE) ===
        if os.path.exists(ai_log_path):
            with open(ai_log_path, "r") as f:
                lines = [line.strip() for line in f if line.strip()]
            
            if len(lines) > 1:
                header = lines[0]
                last_row = lines[-1]
                reader = csv.reader([last_row])
                for row in reader:
                    if len(row) < 5:
                        continue
                    try:
                        imageid_str, timestamp_str, mse, anomaly_str, detected_objects_str = row
                        imageid = int(imageid_str)
                        anomaly = anomaly_str.strip().lower() == "true"
                        timestamp_log = datetime.fromisoformat(timestamp_str)
                        detected_objects = [obj.strip() for obj in detected_objects_str.split(",") if obj.strip()]

                        cur.execute("SELECT 1 FROM Image_Data WHERE imageid = %s", (imageid,))
                        if cur.fetchone() is None:
                            print(f"[AI LOG SKIP] imageid {imageid} not found in Image_Data → skipped.")
                            continue
                        cur.execute("SELECT 1 FROM ai_results WHERE imageid = %s", (imageid,))
                        if cur.fetchone():
                            print(f"[AI LOG SKIP] imageid {imageid} already in ai_results → skipped.")
                            continue

                        gps_id = None
                        cur.execute("""
                            INSERT INTO ai_results (date, anomalystatus, robot_locationid, imageid, robotid, gps_id, objectid, description)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (timestamp_log, anomaly, 1, imageid, 1, gps_id, None, "Inserted from ai_log.txt"))

                        for obj in detected_objects:
                            cur.execute("""
                                INSERT INTO object (objectname, initial_latitude, initial_longitude, new_latitude, new_longitude, time)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """, (obj, 0.0, 0.0, 0.0, 0.0, timestamp_log))

                        action = f"AI_RESULT inserted - ID={imageid} - MSE={mse} - Anomaly={anomaly} - Objects={detected_objects_str}"
                        cur.execute("""
                            INSERT INTO Logs (LogTime, Action, UserID, LogFilePath)
                            VALUES (%s, %s, %s, %s)
                        """, (timestamp_log, action, 2, log_file))
                        conn.commit()
                        print(f"[AI ✓] imageid {imageid} inserted into ai_results.")
                    except Exception as e:
                        conn.rollback()
                        print(f"[HATA] AI_LOG satırı işlenemedi: {e}")

            with open(log_file, "a") as logf:
                logf.write(f"[{timestamp}] AI_LOG processed.\n")
            print("📄 ai_log.txt has been processed into the database.")

    except KeyboardInterrupt:
        print("🚫 Program terminated.")
        break
    except Exception as e:
        print(f"[HATA] General loop error: {e}")

    time.sleep(1)

cur.close()
conn.close()