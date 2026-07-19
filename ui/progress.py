from PyQt6.QtWidgets import QProgressBar


def indeterminate_progress_bar(width: int = None, height: int = None) -> QProgressBar:
    """An indeterminate ("busy") progress bar.

    A 0–0 range makes Qt show a looping animation instead of a percentage. Used wherever
    work has no measurable progress (quiz generation, speech-model download). Pass `width`
    or `height` to fix that dimension.
    """
    bar = QProgressBar()
    bar.setRange(0, 0)
    bar.setTextVisible(False)
    if width is not None:
        bar.setFixedWidth(width)
    if height is not None:
        bar.setFixedHeight(height)
    return bar
