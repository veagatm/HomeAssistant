"""EasyOCR-based Code Enforcement vehicle detection."""

import logging
import numpy as np
import easyocr

log = logging.getLogger(__name__)

TARGET_PHRASES = ["CODE ENFORCEMENT", "CODE ENF"]


class VehicleOCR:
    def __init__(self):
        log.info("Loading EasyOCR (first run downloads model ~100MB)...")
        self.reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        log.info("EasyOCR ready")

    def scan(self, frame: np.ndarray) -> bool:
        """Return True if 'Code Enforcement' text is detected in the frame."""
        try:
            results = self.reader.readtext(frame, detail=0, paragraph=True)
            text = " ".join(results).upper()
            for phrase in TARGET_PHRASES:
                if phrase in text:
                    log.info("OCR match: '%s' found in frame", phrase)
                    return True
        except Exception as e:
            log.warning("OCR error: %s", e)
        return False
