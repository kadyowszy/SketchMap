from typing import Any, Callable

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot


class WorkerSignals(QObject):
    finished = pyqtSignal(int, object)
    error = pyqtSignal(int, str)
    progress = pyqtSignal(int, str)


class PipelineWorker(QRunnable):

    def __init__(self, job_id: int, fn: Callable[..., Any], *args, **kwargs):
        super().__init__()
        self.setAutoDelete(False)
        self.job_id, self.fn, self.args, self.kwargs = job_id, fn, args, kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:
            self.signals.error.emit(self.job_id, str(exc))
            return
        self.signals.finished.emit(self.job_id, result)
