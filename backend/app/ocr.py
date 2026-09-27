"""Tesseract OCR (Bengali + English). Absent Tesseract → OCR silently disabled, images go to the visual path."""
import logging
import threading

from PIL import Image

from . import config

log = logging.getLogger(__name__)
_lock = threading.Lock()
_state: dict = {}


def _init() -> dict:
    with _lock:
        if _state:
            return _state
        _state.update(available=False, langs="", error=None)
        try:
            import pytesseract

            if config.TESSERACT_CMD:
                pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
            installed = set(pytesseract.get_languages(config=""))
            wanted = [lang for lang in config.OCR_LANGS.split("+") if lang in installed]
            if wanted:
                _state.update(available=True, langs="+".join(wanted))
            else:
                _state["error"] = f"none of {config.OCR_LANGS} installed (have {sorted(installed)})"
        except Exception as exc:
            _state["error"] = repr(exc)
        if _state["error"]:
            log.warning("OCR disabled: %s", _state["error"])
        return _state


def status() -> dict:
    return dict(_init())


def extract_text(img: Image.Image) -> str:
    state = _init()
    if not state["available"]:
        return ""
    import pytesseract

    gray = img.convert("L")
    if gray.width < 1000:  # Tesseract (especially Bengali) does much better on larger glyphs
        gray = gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS)
    try:
        return pytesseract.image_to_string(gray, lang=state["langs"], config="--psm 3",
                                           timeout=config.OCR_TIMEOUT_S)
    except Exception as exc:
        log.warning("OCR failed: %r", exc)
        return ""
