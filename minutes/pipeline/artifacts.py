import os
import uuid


def write_text_atomic(content: str, destination: str) -> str:
    directory = os.path.dirname(os.path.abspath(destination))
    os.makedirs(directory, exist_ok=True)
    temporary = f"{destination}.{uuid.uuid4().hex}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            try:
                os.fsync(output.fileno())
            except OSError:
                pass
        os.replace(temporary, destination)
    finally:
        try:
            if os.path.exists(temporary):
                os.remove(temporary)
        except OSError:
            pass
    return destination
