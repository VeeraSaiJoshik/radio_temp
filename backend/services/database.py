import firebase_admin
from firebase_admin import credentials, firestore, db
from firebase_admin.db import Reference as db_ref
from firebase_admin.db import Event as db_event
import os
from models import DBRecord, Image, ImageDataDB, PatientContext
from datetime import datetime

class FirebaseDatabase:
    app_initialized = False
    def __init__(self):
        if not FirebaseDatabase.app_initialized:
            cred = credentials.Certificate(os.getcwd() + "/services/firebase_certificate.json")
            firebase_admin.initialize_app(cred)
            FirebaseDatabase.app_initialized = True
        
        self.fb = firestore.client()
        self.db = db.reference(url="https://radiology-assistant-912c4-default-rtdb.firebaseio.com/")

    def set_rl_data(self, path, data: DBRecord):
        dir = self.db.child(path + "/" + data.id)
        dir.set(data.model_dump(mode="json"))

    def update_data(self, path, data):
        self.db.child(path).update(data)

    def delete_data(self, path):
        self.db.child(path).remove()

    def start_webhook(self):
        def call_back(event: db_event):
            print(event.data)
            if event.event_type == "put" and event.data is not None and event.data != "":
                data = event.data[list(event.data.keys())[0]]
                image = ImageDataDB.model_validate(data)

                with open("./cache.txt", "a") as f:
                    f.write(f"{image.id}:{image.image_features}\n")

        open("./cache.txt", "w+")

        ref: db_ref = self.db.child("images")
        ref.listen(call_back)

if __name__ == "__main__":
    firebase_db = FirebaseDatabase()
    john_smith = PatientContext(
        id="rec_001",
        patient_id="MRN-20481",
        age=45,
        sex="M",
        weight_kg=82.5,
        height_cm=178.0,
        scan_date="3/10/25",
        ordering_physician="Dr. Emily Carter",
        modality_hint="CT",
        scan_reason="Chest pain, rule out pulmonary embolism",
        chief_complaint="Sudden onset chest pain with shortness of breath",
        symptoms=["dyspnea", "chest pain", "tachycardia", "mild fever"],
        symptom_duration_days=2,
        relevant_history=["hypertension", "T2DM", "hyperlipidemia"],
        smoking_status="former",
        family_history=["coronary artery disease", "lung cancer"],
        current_medications=["metformin 1000mg", "lisinopril 10mg", "atorvastatin 40mg"],
        allergies=["penicillin"],
        prior_imaging_summary=(
            "Chest X-ray from 2024-11-15: No acute cardiopulmonary process. "
            "Mild cardiomegaly noted. No pleural effusion."
        ),
        relevant_labs={
            "D-dimer": 3.1,
            "CRP": 52.0,
            "troponin": 0.02,
            "WBC": 11.4,
            "HbA1c": 7.8,
            "creatinine": 1.1,
        },
        is_emergency=True,
        raw_ocr_text=(
            "PATIENT: John Smith | MRN: MRN-20481 | DOB: 1980-03-15 | "
            "SEX: M | WEIGHT: 82.5kg | HEIGHT: 178cm | "
            "ORDERING: Dr. Emily Carter | MODALITY: CT CHEST W/CONTRAST | "
            "DATE: 2025-03-10 | REASON: Chest pain R/O PE | STAT"
        ),
    )
    
    firebase_db.set_rl_data("patients", john_smith)