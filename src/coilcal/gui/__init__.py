"""Qt GUI for coilcal. Run with ``uv run coilcal-gui``."""

from .model import CoilParams, Params, Results, compute
from .richtext import summary_html
from .window import MainWindow, main

__all__ = ["CoilParams", "MainWindow", "Params", "Results", "compute", "main", "summary_html"]
