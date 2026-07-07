import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
STORAGE_SECRET = os.getenv("NICEGUI_STORAGE_SECRET", "change-me-too")

DISCLAIMER = (
    "For educational and research purposes only. This assistant does not replace "
    "professional medical judgment and must not be used to diagnose or treat patients. "
    "All answers are generated strictly from the uploaded document corpus."
)

CATEGORIES = {
    "clinical_guideline": "Clinical guideline",
    "research_paper": "Research paper",
    "sop": "SOP",
    "treatment_protocol": "Treatment protocol",
    "other": "Other",
}
