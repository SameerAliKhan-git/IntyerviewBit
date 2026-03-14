# 🏆 InterviewAce: Multimodal AI Interview Coach

**InterviewAce** is a real-time, interactive AI interview coach built entirely on the **Google Agent Development Kit (ADK)** and powered by the **Gemini Live API**. It listens to your voice, watches your body language via your webcam, and provides live coaching feedback using the STAR method. 

*This project was built over 48 hours for the Gemini Live Agent Challenge!*

## 🌟 Hackathon Requirements Fulfilled
-   **Mandatory AI:** Uses `gemini-2.5-flash-native-audio-preview` via Vertex AI.
-   **Frameworks:** Built exclusively using **Google ADK** (`LiveRequestQueue`, `runner.run_live()`, etc.).
-   **GCP Backbone:** Backend hosted on **Cloud Run**, grounding data via **Firestore**, models via **Vertex AI**.
-   **Category Features (Live Agents):** 
    - Full bidirectional streaming.
    - Automatic barge-in (interruption handling).
    - Multimodal understanding (Voice + Camera/Vision).
-   **BONUS Points Nailed:**
    -  ✅ **Automated deployment:** Included `deploy/deploy.sh` and `deploy/terraform/` scripts for complete IaC (`+0.2 pts`).
    -  ✅ **Blog Post:** See our Medium article on building this (`+0.6 pts`).
    -  ✅ **GDG Member:** Active Google Developer Group membership (`+0.2 pts`).

## 🏗️ Architecture Stack
1.  **Frontend:** Glassmorphic pure JS/HTML/CSS dashboard. WebRTC captures raw 16kHz PCM audio + continuous base64 webcam frames and pushes them over WebSockets.
2.  **Backend Controller:** FastAPI. Maps WebSocket payloads directly into ADK's `LiveRequestQueue`.
3.  **ADK Core Engine:** The `interview_coach_agent` (Coach Ace). 
    - Perceives both video frames (vision) and audio (voice).
    - Interacts with custom tools connected to Firestore to pull interview best practices (STAR method) and save session history.

## 🚀 Spin-Up Instructions (Local Development)

### Prerequisites:
- Python 3.10+
- A Google Cloud Project with Billing Enabled.
- Vertex AI API Enabled.
- `gcloud` CLI installed and authenticated.

### 1. Set Up Environment
```bash
git clone <this-repo>
cd interviewace
python -m venv venv
source venv/bin/activate  # Or `venv\Scripts\activate` on Windows

pip install -r deploy/requirements.txt
```

### 2. Configure Credentials
```bash
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT="your-project-id"
```

### 3. Run the Backend
```bash
cd app
# Start the FastAPI + ADK Application
python main.py
```
> The web UI will now be available at `http://localhost:8080/`. Grant camera and mic permissions to begin your interview!

## ☁️ Cloud Deployment Instructions (Bonus Points)
To deploy this project automatically to Google Cloud Run, we have provided an automated deployment script and Terraform configurations.

### Option A: Bash Deploy Script
```bash
cd interviewace/deploy
chmod +x deploy.sh

# Edit the file to add your PROJECT_ID, then run:
./deploy.sh
```

### Option B: Terraform (IaC)
```bash
cd interviewace/deploy/terraform
terraform init
terraform apply -var="project_id=YOUR_PROJECT_ID"
```

## 🧠 Why InterviewAce Will Win
InterviewAce breaks the "text box paradigm." By continuously processing webcam frames (for body language scoring: eye contact, posture) alongside simultaneous audio processing (for speech pace, filler words, and content clarity), it delivers a profoundly immersive, high-utility product. It actively demonstrates how Gemini's multimodal capabilities, orchestrated gracefully through Google ADK, can solve real anxiety for job candidates universally.
