"""
Face recognition gate - FYP style.
If face_recognition/check_registered_user exists, use it.
Otherwise stub returns True (no gate).
"""

from typing import Optional


def check_face_gate(
    timeout_seconds: int = 30,
    show_camera: bool = False,
    face_recognition_path: Optional[str] = None,
) -> bool:
    """
    Check if registered user is detected. Returns True to allow recording, False to skip.
    Uses check_registered_user from face_recognition if available.
    """
    import sys
    from pathlib import Path

    if face_recognition_path is None:
        project_root = Path(__file__).resolve().parents[2]
        face_recognition_path = str(project_root / "face_recognition")

    if face_recognition_path not in sys.path:
        sys.path.insert(0, face_recognition_path)

    try:
        from check_registered_user import check_registered_user
        return check_registered_user(timeout_seconds=timeout_seconds, show_camera=show_camera)
    except ImportError:
        return True
