import pathlib
import mimetypes

def what(file, h=None):
    file_path = pathlib.Path(file)
    if not file_path.exists():
        return None

    mime, _ = mimetypes.guess_type(file_path)
    if mime:
        if mime.startswith("image/"):
            return mime.split("/")[1]
    return None
