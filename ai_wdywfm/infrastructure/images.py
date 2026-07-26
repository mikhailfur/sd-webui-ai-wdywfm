from __future__ import annotations

import base64
import io
from typing import Any

from PIL import Image

from ai_wdywfm.domain.errors import ValidationError


MAX_PIXELS = 32_000_000


def encode_reference_image(image: Any, maximum_side: int) -> str:
    try:
        if not isinstance(image, Image.Image):
            image = Image.open(image)
        if image.width * image.height > MAX_PIXELS:
            raise ValidationError("Reference image exceeds the 32 megapixel safety limit.")
        clean = image.convert("RGB")
        clean.thumbnail((maximum_side, maximum_side), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        clean.save(output, format="JPEG", quality=90, optimize=True)
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("The reference image could not be safely decoded.") from exc
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
