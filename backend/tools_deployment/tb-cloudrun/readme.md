
Deploy to Cloud Run (Your GCP Project)

Make sure you're inside the folder that contains:
app.py
Dockerfile
requirements.txt
model/ (with pytorch_model.bin, config.json, metadata.json)

Set your GCP project and region:

gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud config set run/region us-central1

Deploy to Cloud Run:
gcloud run deploy tb-xray-classifier --source . --allow-unauthenticated

Cloud Run will:
Build the Docker container
Push it to Google
Deploy it
Print a public HTTPS URL
Save that URL.


check:
curl https://YOUR_CLOUD_RUN_URL/health

Expected response:
ok

Now test prediction with an image:
curl -X POST -F "file=@/path/to/chest_xray.png" https://YOUR_CLOUD_RUN_URL/predict

You should receive JSON like:

{
"prediction": "Tuberculosis",
"scores": {
"Normal": 0.12,
"Tuberculosis": 0.88
}
}

If something fails, check logs:
gcloud run services logs read tb-xray-classifier --limit 50