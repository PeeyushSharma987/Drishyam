import threading
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import cv2
import numpy as np
import requests
import datetime
import time
import easyocr

print("Initializing Jabalpur Tactical Node...")
# Static location for edge deployment
SYS_LAT, SYS_LON = 23.1815, 79.9864
SYS_CITY = "Jabalpur"
SYS_REGION = "Madhya Pradesh"
SYS_COUNTRY = "India"
SYS_ADDRESS = f"{SYS_CITY}, {SYS_REGION}, {SYS_COUNTRY}"

last_alert_time = 0
ALERT_COOLDOWN = 5.0 

# Identity & Access Databases
user_profiles = {
    1: "Peeyush | ID: 4927-A" 
}
AUTHORIZED_PLATES = ["MH12AB1234", "KA01XY9999", "DL8CAB0001", "MH12AB3456"]

print("Setting up robust dataset trainer...")
dataset_dir = "authorized_faces"
cascade_path = "haarcascade_frontalface_default.xml"

# Automatically download Caffe model files if missing
prototxt_path = "deploy.prototxt"
model_path = "res10_300x300_ssd_iter_140000.caffemodel"
if not os.path.exists(prototxt_path) or not os.path.exists(model_path):
    print("Downloading ResNet-10 SSD DNN files...")
    with open(prototxt_path, 'wb') as f: f.write(requests.get("https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt").content)
    with open(model_path, 'wb') as f: f.write(requests.get("https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel").content)

veh_proto = "MobileNetSSD_deploy.prototxt"
veh_model = "MobileNetSSD_deploy.caffemodel"
if not os.path.exists(veh_proto) or not os.path.exists(veh_model):
    print("Downloading Vehicle DNN files...")
    with open(veh_proto, 'wb') as f: f.write(requests.get("https://raw.githubusercontent.com/djmv/MobilNet_SSD_opencv/master/MobileNetSSD_deploy.prototxt").content)
    with open(veh_model, 'wb') as f: f.write(requests.get("https://raw.githubusercontent.com/djmv/MobilNet_SSD_opencv/master/MobileNetSSD_deploy.caffemodel").content)

# Initialize AI Models (GPU Accelerated)
net = cv2.dnn.readNetFromCaffe(prototxt_path, model_path)
net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)

net_vehicles = cv2.dnn.readNetFromCaffe(veh_proto, veh_model)
net_vehicles.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
net_vehicles.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
VEHICLE_CLASSES = ["background", "aeroplane", "bicycle", "bird", "boat", "bottle", "bus", "car", "cat", "chair", "cow", "diningtable", "dog", "horse", "motorbike", "person", "pottedplant", "sheep", "sofa", "train", "tvmonitor"]

print("Loading OCR Engine...")
reader = easyocr.Reader(['en'], gpu=True)

# Train Facial Recognizer
face_cascade = cv2.CascadeClassifier(cascade_path)
recognizer = cv2.face.LBPHFaceRecognizer_create()

if not os.path.exists(dataset_dir):
    os.makedirs(dataset_dir)
    print(f"Created '{dataset_dir}'. Put your photos inside and run again.")
    exit()

evidence_dir = "intrusions"
if not os.path.exists(evidence_dir):
    os.makedirs(evidence_dir)

faces, labels = [], []
for filename in os.listdir(dataset_dir):
    if filename.lower().endswith((".jpg", ".jpeg", ".png")):
        path = os.path.join(dataset_dir, filename)
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None: continue
        
        detected_faces = face_cascade.detectMultiScale(img, scaleFactor=1.1, minNeighbors=4)
        if len(detected_faces) > 0:
            (x, y, w, h) = detected_faces[0]
            face_crop = img[y:y+h, x:x+w]
            face_crop = cv2.equalizeHist(face_crop) # Equalize training data
            faces.append(face_crop)
            labels.append(1)

if len(faces) == 0:
    print(f"Error: No valid faces in '{dataset_dir}'.")
    exit()

recognizer.train(faces, np.array(labels))
print(f"Successfully trained on {len(faces)} photos!")

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

STREAM_URL = "http://192.0.0.4:8080/video"
cap = ThreadedCamera(STREAM_URL)

def trigger_alert(breach_frame):
    try:
        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        temp_filename = f"{evidence_dir}/threat_{timestamp_str}.jpg"
        cv2.imwrite(temp_filename, breach_frame)
        
        with open("master.key", "rb") as key_file:
            key = key_file.read()
            
        with open(temp_filename, "rb") as img_file:
            image_data = img_file.read()
            
        aesgcm = AESGCM(key)
        nonce = os.urandom(12) 
        encrypted_data = aesgcm.encrypt(nonce, image_data, None)
        
        enc_filename = f"{temp_filename}.aes"
        with open(enc_filename, "wb") as enc_file:
            enc_file.write(nonce + encrypted_data)
            
        os.remove(temp_filename)
                
        print("\n" + "="*40)
        print("🚨 THREAT DETECTED: UNAUTHORIZED PERSON")
        print(f"🕒 Time: {timestamp_str}")
        print(f"📍 Location: {SYS_ADDRESS}")
        print(f"📡 Coordinates: Lat {SYS_LAT}, Lon {SYS_LON}")
        print(f"🔒 Evidence ENCRYPTED: {enc_filename}")
        print("="*40 + "\n")
    except Exception as e:
        print(f"🚨 Alert Error: {e}")

print("System ready! Press 'q' to quit.")

frame_count = 0
last_detections = []
last_vehicles = []

while True:
    ret, frame = cap.read()
    if not ret: break
    frame_count += 1
    
    if frame_count % 5 == 0:
        (h, w) = frame.shape[:2]
        
# --- A. Scan for Faces ---
        blob_face = cv2.dnn.blobFromImage(cv2.resize(frame, (600, 600)), 1.0, (600, 600), (104.0, 177.0, 123.0))
        net.setInput(blob_face)
        face_detections = net.forward()
        
        last_detections = []
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 1. Gather raw predictions with a STRICT confidence floor (Kills weak ghost boxes)
        raw_detections = []
        for i in range(0, face_detections.shape[2]):
            conf = face_detections[0, 0, i, 2]
            if conf > 0.85: # Raised from 0.5 to 0.75
                box = face_detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                raw_detections.append((conf, box.astype("int")))
                
        # 2. Sort so the absolute best/truest faces are processed first
        raw_detections.sort(key=lambda x: x[0], reverse=True)
        
        valid_boxes = []

        # 3. Fractional Intersection Filter
        for conf, box in raw_detections:
            (startX, startY, endX, endY) = box
            
            is_ghost = False
            for v_box in valid_boxes:
                (v_startX, v_startY, v_endX, v_endY) = v_box
                
                # Calculate the exact rectangle of the overlap
                ix1, iy1 = max(startX, v_startX), max(startY, v_startY)
                ix2, iy2 = min(endX, v_endX), min(endY, v_endY)
                
                if ix2 > ix1 and iy2 > iy1:
                    intersection_area = (ix2 - ix1) * (iy2 - iy1)
                    current_box_area = (endX - startX) * (endY - startY)
                    
                    # If more than 30% of this box is swallowed by an existing face, delete it
                    if (intersection_area / current_box_area) > 0.30:
                        is_ghost = True
                        break
            
            if not is_ghost:
                valid_boxes.append(box)
                
                box_w, box_h = endX - startX, endY - startY
                pad_x, pad_y = int(box_w * 0.15), int(box_h * 0.15)
                
                # Apply padding safely within screen bounds
                f_startX, f_startY = max(0, startX - pad_x), max(0, startY - pad_y)
                f_endX, f_endY = min(w - 1, endX + pad_x), min(h - 1, endY + pad_y)

                face_roi = gray[f_startY:f_endY, f_startX:f_endX]

                if face_roi.shape[0] > 20 and face_roi.shape[1] > 20:
                    face_roi = cv2.equalizeHist(face_roi)
                    label, distance = recognizer.predict(face_roi)
                    
                    bw, bh = f_endX - f_startX, f_endY - f_startY
                    last_detections.append((f_startX, f_startY, bw, bh, distance, label))
        # --- B. Scan for Vehicles with ALPR ---
        blob_veh = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 0.007843, (300, 300), 127.5)
        net_vehicles.setInput(blob_veh)
        veh_detections = net_vehicles.forward()
        
        last_vehicles = []
        for i in range(veh_detections.shape[2]):
            confidence = veh_detections[0, 0, i, 2]
            class_id = int(veh_detections[0, 0, i, 1])
            
            if confidence > 0.6 and VEHICLE_CLASSES[class_id] in ["car", "bus", "motorbike"]:
                v_box = veh_detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                (vx1, vy1, vx2, vy2) = v_box.astype("int")
                
                vx1, vy1 = max(0, vx1), max(0, vy1)
                vx2, vy2 = min(w - 1, vx2), min(h - 1, vy2)
                
                v_type = VEHICLE_CLASSES[class_id].upper()
                auth_status = "UNKNOWN"
                
                if (vx2 - vx1) > 150 and frame_count % 15 == 0:
                    plate_roi = frame[vy1:vy2, vx1:vx2]
                    gray_plate = cv2.cvtColor(plate_roi, cv2.COLOR_BGR2GRAY)
                    ocr_results = reader.readtext(gray_plate)
                    
                    for (bbox, text, prob) in ocr_results:
                        clean_text = text.replace(" ", "").replace("-", "").upper()
                        if clean_text in AUTHORIZED_PLATES:
                            auth_status = f"AUTHORIZED: {clean_text}"
                            break
                
                last_vehicles.append((vx1, vy1, vx2, vy2, v_type, auth_status))

    # --- 2. MULTI-TARGET DRAWING & ALERTS ---
    current_threats = 0

    for (vx1, vy1, vx2, vy2, v_type, auth_status) in last_vehicles:
        if "AUTHORIZED" in auth_status:
            cv2.rectangle(frame, (vx1, vy1), (vx2, vy2), (0, 255, 0), 2)
            cv2.putText(frame, auth_status, (vx1, vy1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            cv2.rectangle(frame, (vx1, vy1), (vx2, vy2), (255, 0, 0), 2)
            cv2.putText(frame, f"TARGET: {v_type}", (vx1, vy1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

    for (x, y, bw, bh, distance, label) in last_detections:
        if distance < 75: 
            cv2.rectangle(frame, (x, y), (x+bw, y+bh), (0, 255, 0), 2)
            identity_text = user_profiles.get(label, "Unknown User")
            cv2.putText(frame, identity_text, (x, y+bh+25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else: 
            current_threats += 1
            cv2.rectangle(frame, (x, y), (x+bw, y+bh), (0, 0, 255), 2)
            cv2.putText(frame, "UNAUTHORIZED INTRUDER", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

    if current_threats > 0:
        current_time = time.time()
        if (current_time - last_alert_time) > ALERT_COOLDOWN:
            trigger_alert(frame)
            last_alert_time = current_time

    cv2.imshow("Intelligent Border Monitor", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()













