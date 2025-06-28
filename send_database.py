#!/usr/bin/python3

import serial
import os
import time
import psutil
import subprocess
import threading
import json
from datetime import datetime

# ==== AYARLAR ====
ser = serial.Serial("/dev/ttyACM0", 9600, timeout=0.5)
base_path = "/home/mergen/Desktop/Burak_Ibici"

pi4_user = "mergen"
pi4_ip = "10.146.42.252"
pi4_dest_base = "/home/mergen/Desktop/db"

# ==== KLASÖRLER ====
def ensure_dirs():
    os.makedirs(f"{base_path}/Pending/Images", exist_ok=True)
    os.makedirs(f"{base_path}/Pending/Logs", exist_ok=True)

def get_pending_image_path(filename):
    return os.path.join(base_path, "Pending", "Images", filename)

def get_pending_log_path(filename):
    return os.path.join(base_path, "Pending", "Logs", filename)

# ==== JSON ====
def write_json(data, path, mode="w"):
    with open(path, mode) as f:
        if mode == "a":
            f.write(json.dumps(data) + "\n")
        else:
            json.dump(data, f, indent=4)

# ==== SCP GÖNDER ====
def send_file_to_pi4(local_path, remote_folder):
    filename = os.path.basename(local_path)
    remote_path = f"{pi4_user}@{pi4_ip}:{pi4_dest_base}/{remote_folder}/{filename}"

    try:
        result = subprocess.run(
            ["scp", local_path, remote_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10
        )
        if result.returncode == 0:
            os.remove(local_path)
            print(f"[✓] Sent and deleted → {remote_folder}/{filename}")
        else:
            print(f"[!] Failed to send: {filename}\n{result.stderr.decode().strip()}")
    except Exception as e:
        print(f"[!] Exception during send: {e}")

# ==== SİSTEM VERİLERİ ====
def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return f"{int(f.read()) / 1000.0:.1f}°C"
    except:
        return "N/A"

def get_gpu_temp():
    try:
        out = subprocess.check_output(["vcgencmd", "measure_temp"]).decode()
        return out.strip().split('=')[1]
    except:
        return "N/A"

def get_network_speeds():
    net1 = psutil.net_io_counters()
    time.sleep(1)
    net2 = psutil.net_io_counters()
    up = (net2.bytes_sent - net1.bytes_sent) / 1024
    down = (net2.bytes_recv - net1.bytes_recv) / 1024
    return {"Upload (KB/s)": f"{up:.2f}", "Download (KB/s)": f"{down:.2f}"}

def get_system_stats():
    cpu = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory().used / (1024 * 1024)
    net = get_network_speeds()
    return {
        "CPU": f"{cpu:.1f}%",
        "RAM": f"{ram:.1f} MB",
        "CPU Temp": get_cpu_temp(),
        "GPU Temp": get_gpu_temp(),
        **net,
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

# ==== ARDUINO ====
def parse_arduino(line):
    data = {}
    parts = line.replace("DATA:", "").split(" | ")
    for part in parts:
        if part.startswith("Gyro="):
            gx, gy, gz = part.split("=")[1].split(",")
            data["Gyro"] = {"X": gx, "Y": gy, "Z": gz}
        elif part.startswith("ServoAngles="):
            n, h = part.split("=")[1].split(",")
            data["ServoAngles"] = {"Neck": n, "Head": h}
        elif part.startswith("Distance(cm)="):
            d = part.split("=")[1].split(" ")
            data["Distances"] = {kv.split(":")[0]: kv.split(":")[1] for kv in d}
        elif part.startswith("MotorState="):
            data["MotorState"] = part.split("=")[1]
    data["Timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return data

# ==== FOTOĞRAF THREADİ ====
def photo_loop():
    while True:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"photo_{timestamp}.jpg"
        path = get_pending_image_path(filename)

        # Fotoğraf çek
        command = f"libcamera-still -o '{path}' -t 1 --width 1920 --height 1080 --nopreview"
        subprocess.call(command, shell=True)
        print(f"[Frame] Captured → {filename}")

        # Gönderim için ayrı thread başlat
        threading.Thread(target=send_file_to_pi4, args=(path, "Images"), daemon=True).start()

        time.sleep(1)  # Her 1 saniyede bir


# ==== DOSYA GÖNDERİM THREADİ ====
def retry_pending_loop():
    while True:
        for folder, remote in [("Images", "Images"), ("Logs", "Logs")]:
            pending_dir = os.path.join(base_path, "Pending", folder)
            for file in os.listdir(pending_dir):
                local_path = os.path.join(pending_dir, file)
                threading.Thread(target=send_file_to_pi4, args=(local_path, remote), daemon=True).start()

        time.sleep(15)

# ==== ANA DÖNGÜ ====
def main_loop():
    last_arduino = 0
    last_pi5 = 0

    while True:
        now = time.time()

        # Arduino
        if now - last_arduino >= 5:
            if ser.in_waiting > 0:
                try:
                    line = ser.readline().decode("utf-8").strip()
                    if line.startswith("DATA:"):
                        parsed = parse_arduino(line)
                        filename = f"Arduino_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                        path = get_pending_log_path(filename)
                        write_json(parsed, path, mode="w")
                        print(f"[Arduino] Logged → {filename}")
                except:
                    pass
            last_arduino = now

        # Pi5 system
        if now - last_pi5 >= 5:
            stats = get_system_stats()
            filename = "Pi5_Latest.json"
            path = get_pending_log_path(filename)
            write_json(stats, path, mode="w")
            print("[Pi5] Updated system stats.")
            last_pi5 = now

        time.sleep(0.5)

# ==== BAŞLAT ====
ensure_dirs()

threading.Thread(target=photo_loop, daemon=True).start()
threading.Thread(target=retry_pending_loop, daemon=True).start()

try:
    main_loop()
except KeyboardInterrupt:
    print("Program stopped.")
