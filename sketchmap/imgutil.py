import cv2
import numpy as np


def resize_keep_aspect(image: np.ndarray, max_side: int = 1200) -> np.ndarray:
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return image
    scale = max_side / float(longest)
    return cv2.resize(image, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                      interpolation=cv2.INTER_AREA)


def cap_working_resolution(image_bgr: np.ndarray, max_side: int = 1280) -> np.ndarray:
    return resize_keep_aspect(image_bgr, max_side)


def letterbox_to_canvas(image: np.ndarray, target_w: int, target_h: int,
                        pad_color: "int | tuple[int, int, int]" = 255):
    h, w = image.shape[:2]
    scale = min(target_w / float(w), target_h / float(h))
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    if image.ndim == 3:
        color = (pad_color,) * image.shape[2] if isinstance(pad_color, int) else pad_color
        canvas = np.full((target_h, target_w, image.shape[2]), color, dtype=image.dtype)
    else:
        val = pad_color[0] if isinstance(pad_color, tuple) else pad_color
        canvas = np.full((target_h, target_w), val, dtype=image.dtype)
    pad_x, pad_y = (target_w - new_w) // 2, (target_h - new_h) // 2
    canvas[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized
    return canvas, (scale, pad_x, pad_y)


def compute_square_grid_size(image_shape, target_longest_cells: int = 48):
    h, w = image_shape[:2]
    if w >= h:
        return target_longest_cells, max(4, int(round(target_longest_cells * (h / float(w)))))
    return max(4, int(round(target_longest_cells * (w / float(h))))), target_longest_cells
