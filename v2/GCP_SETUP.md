# GCP + GitHub Actions Setup

One-time steps to wire up auto-deploy from GitHub → Cloud Run.

## 1. Prerequisites
- `gcloud` CLI installed and authenticated
- Billing enabled on your GCP project

## 2. Enable APIs
```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  --project YOUR_PROJECT_ID
```

## 3. Create Artifact Registry repository
```bash
gcloud artifacts repositories create trackalong \
  --repository-format=docker \
  --location=australia-southeast1 \
  --project YOUR_PROJECT_ID
```

## 4. Create a service account for CI
```bash
gcloud iam service-accounts create trackalong-deployer \
  --display-name="TrackAlong CI Deployer" \
  --project YOUR_PROJECT_ID
```

Grant it the minimum required roles:
```bash
PROJECT=YOUR_PROJECT_ID
SA=trackalong-deployer@${PROJECT}.iam.gserviceaccount.com

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:${SA}" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:${SA}" \
  --role="roles/artifactregistry.writer"

gcloud iam service-accounts add-iam-policy-binding \
  ${PROJECT}@appspot.gserviceaccount.com \
  --member="serviceAccount:${SA}" \
  --role="roles/iam.serviceAccountUser" \
  --project $PROJECT
```

## 5. Configure Workload Identity Federation
```bash
# Create WIF pool
gcloud iam workload-identity-pools create github-pool \
  --location=global \
  --project YOUR_PROJECT_ID

# Create OIDC provider bound to your repo
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --workload-identity-pool=github-pool \
  --location=global \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="attribute.repository=='edwardolivier/TrackAlong'" \
  --project YOUR_PROJECT_ID

# Allow the pool to impersonate the service account
gcloud iam service-accounts add-iam-policy-binding \
  trackalong-deployer@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/YOUR_PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/edwardolivier/TrackAlong" \
  --project YOUR_PROJECT_ID
```

Get your project number:
```bash
gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"
```

## 6. Add GitHub repository secrets

In GitHub → Settings → Secrets and variables → Actions, add:

| Secret | Value |
|--------|-------|
| `GCP_PROJECT_ID` | Your GCP project ID |
| `GCP_WIF_PROVIDER` | `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
| `GCP_SERVICE_ACCOUNT` | `trackalong-deployer@YOUR_PROJECT_ID.iam.gserviceaccount.com` |
| `GOOGLE_CLIENT_ID` | OAuth 2.0 client ID (from GCP Console → APIs & Services → Credentials) |
| `ALLOWED_EMAILS` | Comma-separated list of authorised Google emails |

## 7. Create OAuth client ID
1. GCP Console → APIs & Services → Credentials → Create Credentials → OAuth client ID
2. Application type: **Web application**
3. Authorised JavaScript origins: your Cloud Run URL (get it after first deploy)
4. Copy the client ID → `GOOGLE_CLIENT_ID` secret

## 8. First deploy
Push any change to `main` that touches `v2/` and watch the Actions tab.
The Cloud Run URL will be printed in the workflow logs.
