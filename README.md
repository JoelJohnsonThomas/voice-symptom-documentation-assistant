# Voice Symptom Intake & Documentation Assistant

A HIPAA-compliant, AI-powered voice intake system that streamlines patient symptom reporting and automates clinical documentation.

![Project Banner](https://img.shields.io/badge/Status-Prototype-blue) ![License](https://img.shields.io/badge/License-MIT-green) ![Compliance](https://img.shields.io/badge/Compliance-HIPAA%20Ready-red)

## 🩺 Overview

The **Voice Symptom Intake Assistant** bridges the gap between patient reporting and clinical documentation. It allows patients to describe their symptoms naturally via voice or text, and uses advanced AI to instantly generate structured medical records and SOAP notes for clinician review.

This project was built to demonstrate how **specialized medical AI models** (MedASR & MedGemma) can reduce administrative burden while maintaining strict accuracy and compliance standards.

## ✨ Key Features

- **🗣️ Voice-First Interface:** Browser-based audio recording with real-time visualization.
- **📝 Medical Transcription:** Utilizes **Google's MedASR** for highly accurate medical speech-to-text.
- **🧠 Intelligent Extraction:** Uses **MedGemma 1.5** (LLM) to extract:
  - Chief Complaint
  - Symptom Details (Onset, Duration, Severity, Location)
  - Patient Uncertainty ("maybe", "not sure")
- **📋 Automated Documentation:** Generates a professional **SOAP Note (Subjective)** section.
- **✅ Verification Loop:** Includes original audio playback for clinicians to verify transcription accuracy.
- **🛡️ Compliance-Focused:** Explicitly designed as an administrative aid (non-diagnostic), with mandatory clinician review flags.

## 🛠️ Technology Stack

### Backend
- **Python 3.10+**
- **FastAPI** - High-performance asynchronous API framework
- **PyTorch** - Deep learning inference
- **Transformers (Hugging Face)** - Model management

### AI Models
- **ASR:** `nvidia/stt_en_conformer_transducer_xlarge` (or Google MedASR equivalent)
- **LLM:** `google/medgemma-1.5-2b` (Medical-tuned Gemma model)

### Frontend
- **HTML5 / CSS3** - Custom "Medical Grade" design system (Inter font, accessibility focused)
- **JavaScript (Vanilla)** - Audio recording API, canvas visualization, async state management

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- NVidia GPU (Recommended for model inference) - *Can run on CPU but slower*

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/voice-symptom-intake.git
   cd voice-symptom-intake
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   Copy `.env.example` to `.env` and configure your Hugging Face token (if required for gated models).
   ```bash
   cp .env.example .env
   ```

### Running the Application

Start the FastAPI server:
```bash
python -m uvicorn app.main:app --reload
```
Open your browser at `http://localhost:8000`.

## 🔒 Compliance & Safety

This tool adheres to **Google Health AI Developer Foundations** principles:
1. **Administrative Support:** Specifically labeled as documentation support, NOT a medical device.
2. **Human in the Loop:** All outputs are flagged "Requires Clinician Review".
3. **No Diagnosis:** Prompts are strictly engineered to extract information, not offer advice.

## 📄 License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

---
*Built with ❤️ for better healthcare workflows.*
