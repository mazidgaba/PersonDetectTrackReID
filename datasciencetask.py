# -*- coding: utf-8 -*-
"""DataScienceTask.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1p4_F1tMf8x24WJtcdM0cNlXLvxWimBJh
"""

# Cell 1: Install Dependencies
!pip install ultralytics torchreid faiss-cpu opencv-python-headless matplotlib

# Cell 2: Import Libraries
import os
import cv2
import numpy as np
from ultralytics import YOLO
import faiss
from collections import defaultdict
import torch
from torchreid import models, utils
from torchvision import transforms
import matplotlib.pyplot as plt
from IPython.display import display, clear_output

# Verify GPU availability
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU device: {torch.cuda.get_device_name(0)}")

# Cell 3: PersonTracker Class Definition
class PersonTracker:
    def __init__(self, reid_model_path="/content/osnet_x1_0_imagenet.pth"):
        # Initialize YOLO model (use GPU if available)
        self.detector = YOLO('yolov8n.pt')
        if torch.cuda.is_available():
            self.detector.to('cuda')

        # Initialize FAISS index
        self.dimension = 512
        self.index = faiss.IndexFlatL2(self.dimension)

        # Storage for embeddings and IDs
        self.person_embeddings = defaultdict(list)
        self.next_id = 0

        # Initialize OSNet ReID model
        self.reid_model = models.build_model(
            name='osnet_x1_0',
            num_classes=1,
            pretrained=True
        )
        if not os.path.exists(reid_model_path):
            # Download pretrained weights if not present
            !gdown "https://drive.google.com/uc?id=1LaG1EJpHrxdAxKnSCJ_i0u-nbxSAeiFY" -O {reid_model_path}
        utils.load_pretrained_weights(self.reid_model, reid_model_path)
        if torch.cuda.is_available():
            self.reid_model.cuda()
        self.reid_model.eval()

        # Image transforms for ReID
        self.transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((256, 128)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

    def get_reid_embedding(self, crop):
        try:
            crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            img = self.transform(crop_rgb)
            img = img.unsqueeze(0)
            if torch.cuda.is_available():
                img = img.cuda()
            with torch.no_grad():
                embedding = self.reid_model(img)
            return embedding.squeeze().cpu().numpy()
        except Exception as e:
            print(f"Error in embedding extraction: {e}")
            return np.zeros(self.dimension, dtype=np.float32)

    def match_reid_embedding(self, embedding, threshold=0.7):
        if self.index.ntotal == 0:
            return None
        distances, indices = self.index.search(embedding.reshape(1, -1), 1)
        if distances[0][0] > threshold:
            return None
        return indices[0][0]

    def process_frame(self, frame):
        # Detect and track persons
        results = self.detector.track(
            source=frame,
            persist=True,
            classes=[0],  # Person class
            tracker='bytetrack.yaml',
            device='cuda' if torch.cuda.is_available() else 'cpu'
        )

        # Handle no detections or no track IDs
        if not results[0].boxes or results[0].boxes.id is None:
            return frame

        boxes = results[0].boxes.xyxy.cpu().numpy()
        track_ids = results[0].boxes.id.cpu().numpy()

        for box, track_id in zip(boxes, track_ids):
            x1, y1, x2, y2 = map(int, box[:4])
            person_crop = frame[y1:y2, x1:x2]
            embedding = self.get_reid_embedding(person_crop)
            matched_id = self.match_reid_embedding(embedding)
            if matched_id is None:
                matched_id = self.next_id
                self.next_id += 1
                self.index.add(embedding.reshape(1, -1))
                self.person_embeddings[matched_id].append(embedding)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"ID: {matched_id}", (x1, y1-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        return frame

# Cell 4: Process Video Function
def process_video(video_path, output_path='/content/labeled_output.mp4'):
    tracker = PersonTracker()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video at {video_path}")
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Total frames: {total_frames}, FPS: {fps}")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_count = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        processed_frame = tracker.process_frame(frame)
        out.write(processed_frame)
        if frame_count % 50 == 0:
            plt.figure(figsize=(10, 6))
            plt.imshow(cv2.cvtColor(processed_frame, cv2.COLOR_BGR2RGB))
            plt.axis('off')
            plt.title(f'Frame {frame_count}')
            display(plt.gcf())
            clear_output(wait=True)  # Clear previous output in Colab
        frame_count += 1
        print(f"Processed frame {frame_count}/{total_frames}", end='\r')

    cap.release()
    out.release()
    print(f"\nVideo processing complete. Output saved to {output_path}")

# Cell 5: Upload Video and Run Processing
from google.colab import files
uploaded = files.upload()  # Upload Building_K_Cam1.mp4 here

video_path = "/content/Building_K_Cam1.mp4"
output_path = "/content/labeled_output.mp4"
process_video(video_path, output_path)

# Cell 6: Download Output Video
files.download('/content/labeled_output.mp4')

# Cell 7: Display Sample Frame (Optional)
def display_sample_frame(video_path):
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 100)
    ret, frame = cap.read()
    if ret:
        plt.figure(figsize=(12, 8))
        plt.imshow(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        plt.axis('off')
        plt.title('Sample Frame from Output')
        display(plt.gcf())
    cap.release()

display_sample_frame(output_path)

!ls /content

from google.colab import drive
drive.mount('/content/drive')

