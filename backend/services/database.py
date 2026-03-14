import firebase_admin
from firebase_admin import credentials, firestore, db
from firebase_admin.db import Reference as db_ref
from firebase_admin.db import Event as db_event
import os
import multiprocessing
from models import DBRecord, Image, ImageDataDB, PatientContext
from datetime import datetime


def _firestore_lookup_worker(cert_path, db_url, first_name, last_name, result_queue):
    """Top-level function (required for multiprocessing pickling) that queries Firestore."""
    try:
        import firebase_admin as _fa
        from firebase_admin import credentials as _creds, firestore as _fs
        from models import PatientContext as _PC
        if not _fa._apps:
            _cred = _creds.Certificate(cert_path)
            _fa.initialize_app(_cred)
        _fb = _fs.client()
        users_ref = _fb.collection("users")
        for doc in users_ref.stream():
            patient = _PC.model_validate({**doc.to_dict(), "id": doc.id})
            if (patient.patient_first_name or "").lower() == first_name.lower() and \
               (patient.patient_last_name or "").lower() == last_name.lower():
                result_queue.put(patient.id)
                return
        result_queue.put("")
    except Exception as e:
        print(f"Firestore worker error: {e}")
        result_queue.put("")

class FirebaseDatabase:
    app_initialized = False
    def __init__(self):
        if not FirebaseDatabase.app_initialized:
            cert_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firebase_certificate.json")
            cred = credentials.Certificate(cert_path)
            firebase_admin.initialize_app(cred)
            FirebaseDatabase.app_initialized = True
        
        self.fb = firestore.client()
        self.db = db.reference(url="https://radiology-assistant-912c4-default-rtdb.firebaseio.com/")

    def set_rl_data(self, path, data: DBRecord):
        dir = self.db.child(path + "/" + data.id)
        dir.set(data.model_dump(mode="json"))
    
    def get_user_id_by_first_name(self, first_name, last_name) -> str | None:
        print("I started")
        cert_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firebase_certificate.json")
        db_url = "https://radiology-assistant-912c4-default-rtdb.firebaseio.com/"
        result_queue = multiprocessing.Queue()
        proc = multiprocessing.Process(
            target=_firestore_lookup_worker,
            args=(cert_path, db_url, first_name, last_name, result_queue)
        )
        proc.start()
        proc.join(timeout=15)
        if proc.is_alive():
            print(f"Warning: Firestore query timed out looking up {first_name} {last_name}. Using empty user_id.")
            proc.terminate()
            proc.join()
            return ""
        result = result_queue.get() if not result_queue.empty() else ""
        return result

    def get_rl_data(self, path) -> dict | None:
        return self.db.child(path).get()

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
                    f.write(f"{image.id}|{image.user_id}|{image.image_features}\n")

        open("./cache.txt", "w+")

        ref: db_ref = self.db.child("images")
        ref.listen(call_back)

if __name__ == "__main__":
    firebase_db = FirebaseDatabase()
    john_smith = PatientContext(
        id="rec_001",
        patient_id="MRN-20481",
        patient_first_name="John",
        patient_last_name="Smith",
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

    firebase_db = FirebaseDatabase()
    firebase_db.get_user_id_by_first_name("asdfasdf", "asdfasdf")