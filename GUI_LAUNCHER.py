import tkinter as tk
from PIL import Image, ImageTk
import threading
import os
import time
import datetime
import numpy as np
import cv2
import easyocr
import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ==========================================
# 1. HARDWARE CAMERA THREAD
# ==========================================
class ThreadedCamera:
    def __init__(self, src=0):
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.ret, self.frame = self.cap.read()
        self.stopped = False
        threading.Thread(target=self.update, daemon=True).start()

    def update(self):
        while not self.stopped:
            self.ret, self.frame = self.cap.read()

    def read(self):
        return self.ret, self.frame

    def release(self):
        self.stopped = True
        self.cap.release()

# ==========================================
# 2. TACTICAL GUI & AI INTEGRATION
# ==========================================
class TacticalDashboardApp:
    def __init__(self, window):
        self.window = window
        self.window.title("CIBMS // Tactical Command")
        self.window.geometry("1400x900")
        self.window.configure(bg="#020617") # Deep tactical black/blue

        # Identity Mapping & Whitelists
        self.user_profiles = {1: "Peeyush | ID: 4927-A"}
        self.AUTHORIZED_PLATES = ["MH12AB1234", "KA01XY9999", "DL8CAB0001"]
        self.VEHICLE_CLASSES = ["background", "aeroplane", "bicycle", "bird", "boat", "bottle", "bus", "car", "cat", "chair", "cow", "diningtable", "dog", "horse", "motorbike", "person", "pottedplant", "sheep", "sofa", "train", "tvmonitor"]

        # State Variables
        self.evidence_dir = "intrusions"
        os.makedirs(self.evidence_dir, exist_ok=True)
        self.last_alert_time = 0
        self.ALERT_COOLDOWN = 5.0
        self.frame_count = 0
        self.last_detections = []
        self.last_vehicles = []
        
        self.init_ai_models()
        self.build_ui()

        # Connect Primary Stream (Replace 0 with your IP camera URL if needed)
        self.cap = ThreadedCamera(0)
        
        # Start Master Loop
        self.process_stream()

    def init_ai_models(self):
        print("Loading AI Models...")
        self.net_faces = cv2.dnn.readNetFromCaffe("deploy.prototxt", "res10_300x300_ssd_iter_140000.caffemodel")
        self.net_vehicles = cv2.dnn.readNetFromCaffe("MobileNetSSD_deploy.prototxt", "MobileNetSSD_deploy.caffemodel")
        self.reader = easyocr.Reader(['en'], gpu=False)
        
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        face_cascade = cv2.CascadeClassifier("haarcascade_frontalface_default.xml")
        
        # Train LBPH
        dataset_dir = "authorized_faces"
        faces, labels = [], []
        if os.path.exists(dataset_dir):
            for filename in os.listdir(dataset_dir):
                if filename.lower().endswith((".jpg", ".jpeg", ".png")):
                    path = os.path.join(dataset_dir, filename)
                    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                    if img is None: continue
                    detected = face_cascade.detectMultiScale(img, scaleFactor=1.1, minNeighbors=4)
                    if len(detected) > 0:
                        (x, y, w, h) = detected[0]
                        faces.append(img[y:y+h, x:x+w])
                        labels.append(1)
        if len(faces) > 0:
            self.recognizer.train(faces, np.array(labels))

        # Generate a master key for AES if missing
        if not os.path.exists("master.key"):
            with open("master.key", "wb") as f:
                f.write(os.urandom(32))

    def build_ui(self):
        # 1. Header
        header_frame = tk.Frame(self.window, bg="#0f172a", highlightthickness=1, highlightbackground="#334155")
        header_frame.pack(fill=tk.X, pady=5, padx=5)
        
        tk.Label(header_frame, text="INTELLIGENT BORDER MONITOR // COMMAND CENTER", font=("Consolas", 16, "bold"), fg="#38bdf8", bg="#0f172a").pack(side=tk.LEFT, padx=15, pady=10)
        tk.Label(header_frame, text="📍 LOCATION: GUNA, MADHYA PRADESH, INDIA", font=("Consolas", 12, "bold"), fg="#94a3b8", bg="#0f172a").pack(side=tk.RIGHT, padx=15)

        # 2. Main Content Wrapper
        content = tk.Frame(self.window, bg="#020617")
        content.pack(fill=tk.BOTH, expand=True, padx=5)

        # --- LEFT: Camera Grid ---
        cam_grid = tk.Frame(content, bg="#020617")
        cam_grid.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.cam_labels = []
        self.cam_frames = []
        for i in range(4):
            row, col = i // 2, i % 2
            frame = tk.Frame(cam_grid, bg="#0f172a", highlightthickness=2, highlightbackground="#334155")
            frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            
            cam_title = f"CAM 0{i+1} // " + ("ACTIVE AI NODE" if i == 3 else "PERIMETER SECURE")
            tk.Label(frame, text=cam_title, font=("Consolas", 10), fg="#22c55e", bg="#0f172a").pack(anchor=tk.NW, padx=5, pady=2)
            
            lbl = tk.Label(frame, bg="black")
            lbl.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            self.cam_labels.append(lbl)
            self.cam_frames.append(frame)

        cam_grid.columnconfigure(0, weight=1)
        cam_grid.columnconfigure(1, weight=1)
        cam_grid.rowconfigure(0, weight=1)
        cam_grid.rowconfigure(1, weight=1)

        # --- RIGHT: Alert & Telemetry Panel ---
        alert_panel = tk.Frame(content, width=400, bg="#0f172a", highlightthickness=1, highlightbackground="#334155")
        alert_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        alert_panel.pack_propagate(False)

        # Threat Status
        self.lbl_threat_status = tk.Label(alert_panel, text="THREAT LEVEL: NOMINAL", font=("Consolas", 14, "bold"), fg="#22c55e", bg="#0f172a", pady=15)
        self.lbl_threat_status.pack(fill=tk.X)

        # Snapshot Display
        tk.Label(alert_panel, text="LATEST INTRUDER SNAPSHOT", font=("Consolas", 10), fg="#94a3b8", bg="#0f172a").pack(pady=5)
        self.lbl_snapshot = tk.Label(alert_panel, bg="black", width=300, height=200)
        self.lbl_snapshot.pack(pady=5, padx=20)

        # Event Log
        tk.Label(alert_panel, text="SYSTEM EVENT LOG", font=("Consolas", 10), fg="#94a3b8", bg="#0f172a").pack(pady=10)
        self.event_log = tk.Listbox(alert_panel, bg="#020617", fg="#38bdf8", font=("Consolas", 9), highlightthickness=0, selectbackground="#334155")
        self.event_log.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        self.log_event("SYSTEM INITIALIZED. VAULT SECURED.")

    def log_event(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.event_log.insert(0, f"[{timestamp}] {message}")
        if self.event_log.size() > 50:
            self.event_log.delete(50, tk.END)

    def process_alert(self, breach_frame):
        # 1. Update UI Snapshot
        display_snap = cv2.resize(breach_frame, (300, 200))
        snap_img = ImageTk.PhotoImage(image=Image.fromarray(cv2.cvtColor(display_snap, cv2.COLOR_BGR2RGB)))
        self.lbl_snapshot.config(image=snap_img)
        self.lbl_snapshot.image = snap_img 
        
        self.log_event("⚠️ INTRUSION DETECTED ON CAM 04")
        self.log_event("🔒 ENCRYPTING FORENSIC EVIDENCE...")

        # 2. Background Encryption Pipeline
        threading.Thread(target=self.encrypt_payload, args=(breach_frame,), daemon=True).start()

    def encrypt_payload(self, frame):
        try:
            timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            temp_path = f"{self.evidence_dir}/threat_{timestamp_str}.jpg"
            cv2.imwrite(temp_path, frame)

            with open("master.key", "rb") as kf: key = kf.read()
            with open(temp_path, "rb") as imf: raw_bytes = imf.read()

            aesgcm = AESGCM(key)
            nonce = os.urandom(12)
            encrypted_payload = aesgcm.encrypt(nonce, raw_bytes, None)

            enc_path = f"{temp_path}.aes"
            with open(enc_path, "wb") as f: f.write(nonce + encrypted_payload)
            os.remove(temp_path)
            
            # Use window.after to safely update the GUI from a background thread
            self.window.after(0, lambda: self.log_event(f"✅ VAULT SEALED: {enc_path}"))
        except Exception as e:
            self.window.after(0, lambda: self.log_event(f"❌ ENCRYPTION FAILED: {e}"))

    def process_stream(self):
        ret, frame = self.cap.read()
        if not ret or frame is None:
            self.window.after(15, self.process_stream)
            return

        self.frame_count += 1
        h, w = frame.shape[:2]
        current_threats = 0

        # === AI PROCESSING PIPELINE (Every 5th frame) ===
        if self.frame_count % 5 == 0:
            # Face Detection
            blob_face = cv2.dnn.blobFromImage(cv2.resize(frame, (400, 400)), 1.0, (400, 400), (104.0, 177.0, 123.0))
            self.net_faces.setInput(blob_face)
            face_detections = self.net_faces.forward()

            self.last_detections = []
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            for i in range(face_detections.shape[2]):
                if face_detections[0, 0, i, 2] > 0.4:
                    box = face_detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                    (startX, startY, endX, endY) = box.astype("int")
                    startX, startY = max(0, startX), max(0, startY)
                    endX, endY = min(w - 1, endX), min(h - 1, endY)

                    face_roi = gray[startY:endY, startX:endX]
                    if face_roi.shape[0] > 20 and face_roi.shape[1] > 20:
                        label, conf = self.recognizer.predict(face_roi)
                        self.last_detections.append((startX, startY, endX-startX, endY-startY, conf, label))

            # Vehicle Detection
            blob_veh = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5)
            self.net_vehicles.setInput(blob_veh)
            veh_detections = self.net_vehicles.forward()

            self.last_vehicles = []
            for i in range(veh_detections.shape[2]):
                if veh_detections[0, 0, i, 2] > 0.6:
                    class_id = int(veh_detections[0, 0, i, 1])
                    if self.VEHICLE_CLASSES[class_id] in ["car", "bus", "motorbike"]:
                        v_box = veh_detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                        vx1, vy1, vx2, vy2 = np.clip(v_box.astype("int"), [0, 0, 0, 0], [w-1, h-1, w-1, h-1])
                        self.last_vehicles.append((vx1, vy1, vx2, vy2, self.VEHICLE_CLASSES[class_id].upper(), "UNKNOWN"))

        # === OVERLAY RENDER ===
        ai_frame = frame.copy()

        for (vx1, vy1, vx2, vy2, v_type, auth) in self.last_vehicles:
            cv2.rectangle(ai_frame, (vx1, vy1), (vx2, vy2), (255, 0, 0), 2)
            cv2.putText(ai_frame, f"TARGET: {v_type}", (vx1, vy1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

        for (x, y, bw, bh, confidence, label) in self.last_detections:
            if confidence < 67:
                cv2.rectangle(ai_frame, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
                cv2.putText(ai_frame, self.user_profiles.get(label, "AUTH"), (x, y + bh + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                current_threats += 1
                cv2.rectangle(ai_frame, (x, y), (x + bw, y + bh), (0, 0, 255), 2)
                cv2.putText(ai_frame, "INTRUDER", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        # === TACTICAL UI UPDATES ===
        if current_threats > 0:
            self.lbl_threat_status.config(text="THREAT LEVEL: CRITICAL", fg="#ef4444")
            self.cam_frames[3].config(highlightbackground="#ef4444") # Red highlight for CAM 04
            
            now = time.time()
            if (now - self.last_alert_time) > self.ALERT_COOLDOWN:
                self.process_alert(ai_frame)
                self.last_alert_time = now
        else:
            self.lbl_threat_status.config(text="THREAT LEVEL: NOMINAL", fg="#22c55e")
            self.cam_frames[3].config(highlightbackground="#334155")

        # === MULTIPLEXING VIDEO FEEDS ===
        # Convert frames to GUI format
        rgb_raw = cv2.cvtColor(cv2.resize(frame, (400, 300)), cv2.COLOR_BGR2RGB)
        rgb_ai = cv2.cvtColor(cv2.resize(ai_frame, (400, 300)), cv2.COLOR_BGR2RGB)
        
        raw_img = ImageTk.PhotoImage(image=Image.fromarray(rgb_raw))
        ai_img = ImageTk.PhotoImage(image=Image.fromarray(rgb_ai))

        # CAM 01-03: Raw observation feeds
        for i in range(3):
            self.cam_labels[i].config(image=raw_img)
            self.cam_labels[i].image = raw_img
            
        # CAM 04: Active AI Analysis feed
        self.cam_labels[3].config(image=ai_img)
        self.cam_labels[3].image = ai_img

        self.window.after(15, self.process_stream)

if __name__ == "__main__":
    root = tk.Tk()
    app = TacticalDashboardApp(root)
    root.mainloop()