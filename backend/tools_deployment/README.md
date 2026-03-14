# Medical AI Models — GCP Cloud Run Deployments

**GCP Project:** `tb-xray-app`
**Region:** `us-central1`

All models are deployed as separate Cloud Run services within the same project.

---

## Deploy Commands

> Run each from inside its folder. Always include `--memory 2Gi --cpu 2`.

### TB Classifier
```bash
cd tb-cloudrun
gcloud run deploy tb-xray-classifier --source . --allow-unauthenticated --memory 2Gi --cpu 2
```

### Pneumonia Classifier
```bash
cd pneumonia-cloudrun
gcloud run deploy pneumonia-classifier --source . --allow-unauthenticated --memory 2Gi --cpu 2
```

### Alzheimers Classifier
```bash
cd alzheimers-cloudrun
gcloud run deploy alzheimers-classifier --source . --allow-unauthenticated --memory 2Gi --cpu 2
```

### Knee OA Classifier
```bash
cd knee-oa-cloudrun
gcloud run deploy knee-oa-classifier --source . --allow-unauthenticated --memory 2Gi --cpu 2
```

### COVID CXR Classifier
```bash
cd covid-cxr-cloudrun
gcloud run deploy covid-cxr-classifier --source . --allow-unauthenticated --memory 2Gi --cpu 2
```

---

## Service URLs

| Model | URL |
|-------|-----|
| TB | `https://tb-xray-classifier-1021943706658.us-central1.run.app` |
| Pneumonia | TBD after deploy |
| Alzheimers | TBD after deploy |
| Knee OA | TBD after deploy |
| COVID CXR | TBD after deploy |

---

## Health Check

```bash
# TB
curl https://tb-xray-classifier-1021943706658.us-central1.run.app/health

# Pneumonia
curl https://pneumonia-classifier-1021943706658.us-central1.run.app/health

# Alzheimers
curl https://alzheimers-classifier-1021943706658.us-central1.run.app/health

# Knee OA
curl https://knee-oa-classifier-1021943706658.us-central1.run.app/health

# COVID CXR
curl https://covid-cxr-classifier-1021943706658.us-central1.run.app/health
```

Expected response: `ok`

---

## Predict (send an image)

```bash
# TB
curl -X POST -F "file=@/path/to/image.png" \
  https://tb-xray-classifier-1021943706658.us-central1.run.app/predict

# Pneumonia
curl -X POST -F "file=@/path/to/image.png" \
  https://pneumonia-classifier-1021943706658.us-central1.run.app/predict

# Alzheimers
curl -X POST -F "file=@/path/to/image.png" \
  https://alzheimers-classifier-1021943706658.us-central1.run.app/predict

# Knee OA
curl -X POST -F "file=@/path/to/image.png" \
  https://knee-oa-classifier-1021943706658.us-central1.run.app/predict

# COVID CXR
curl -X POST -F "file=@/path/to/image.png" \
  https://covid-cxr-classifier-1021943706658.us-central1.run.app/predict
```

---

## Check Logs (if something fails)

```bash
gcloud run services logs read tb-xray-classifier --limit 50
gcloud run services logs read pneumonia-classifier --limit 50
gcloud run services logs read alzheimers-classifier --limit 50
gcloud run services logs read knee-oa-classifier --limit 50
gcloud run services logs read covid-cxr-classifier --limit 50
```
