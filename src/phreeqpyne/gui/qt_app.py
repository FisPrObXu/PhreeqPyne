"""Qt-based interactive parameter editor for PhreeqPyne scenarios.

This module is optional and requires installing the ``gui`` extra.  It is not
imported by the package or CLI unless the user explicitly runs ``phreeqpyne gui``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from phreeqpyne.config import ModelConfig, default_model_config
from phreeqpyne.phreeqc_builder import build_phreeqc_script
from phreeqpyne.runner import run_simulation
from phreeqpyne.simulations import list_simulations


class ScenarioEditor(QMainWindow):
    """Small Qt window for editing common model parameters."""

    def __init__(self) -> None:
        super().__init__()
        self.config = default_model_config()
        self.setWindowTitle("PhreeqPyne Scenario Editor")
        self._build_form()
        self._load_config_to_fields()

    def _build_form(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        workflow_names = ", ".join(f"{item.kind} ({item.display_name})" for item in list_simulations())
        layout.addWidget(QLabel(f"Available workflows: {workflow_names}"))

        form = QFormLayout()
        self.dll_path = QLineEdit()
        self.database_path = QLineEdit()
        self.output_dir = QLineEdit()
        self.n_cells = QSpinBox()
        self.n_cells.setRange(1, 10000)
        self.n_stages = QSpinBox()
        self.n_stages.setRange(1, 1000)
        self.stage_shifts = QLineEdit()
        self.temperature = QLineEdit()
        self.pressure = QLineEdit()
        self.ph = QLineEdit()
        self.au = QLineEdit()

        form.addRow("IPhreeqc DLL/SO", self.dll_path)
        form.addRow("Database", self.database_path)
        form.addRow("Output directory", self.output_dir)
        form.addRow("Cells", self.n_cells)
        form.addRow("Stages", self.n_stages)
        form.addRow("Stage shifts (comma separated)", self.stage_shifts)
        form.addRow("Boundary temperature", self.temperature)
        form.addRow("Boundary pressure", self.pressure)
        form.addRow("Boundary pH", self.ph)
        form.addRow("Au(3) concentration", self.au)
        layout.addLayout(form)

        browse_row = QHBoxLayout()
        config_load = QPushButton("Load config")
        config_load.clicked.connect(self.load_config)
        config_save = QPushButton("Save config")
        config_save.clicked.connect(self.save_config)
        browse_row.addWidget(config_load)
        browse_row.addWidget(config_save)
        layout.addLayout(browse_row)

        action_row = QHBoxLayout()
        render_script = QPushButton("Render PHREEQC script")
        render_script.clicked.connect(self.render_script)
        run_button = QPushButton("Run simulation")
        run_button.clicked.connect(self.run_model)
        action_row.addWidget(render_script)
        action_row.addWidget(run_button)
        layout.addLayout(action_row)

        self.status = QLabel("Ready")
        layout.addWidget(self.status)
        self.setCentralWidget(root)

    def _load_config_to_fields(self) -> None:
        self.dll_path.setText(self.config.runtime.dll_path)
        self.database_path.setText(self.config.runtime.database_path)
        self.output_dir.setText(self.config.runtime.output_dir)
        self.n_cells.setValue(self.config.n_cells)
        self.n_stages.setValue(self.config.n_stages)
        self.stage_shifts.setText(", ".join(str(value) for value in self.config.stage_shifts))
        self.temperature.setText(str(self.config.boundary_base.get("temp", "")))
        self.pressure.setText(str(self.config.boundary_base.get("pressure", "")))
        self.ph.setText(str(self.config.boundary_base.get("pH", "")))
        au_cfg = self.config.boundary_interpolation.get("Au(3)", {})
        self.au.setText(str(au_cfg.get("start", "")))

    def _fields_to_config(self) -> ModelConfig:
        config = self.config
        config.runtime.dll_path = self.dll_path.text().strip()
        config.runtime.database_path = self.database_path.text().strip()
        config.runtime.output_dir = self.output_dir.text().strip() or "."
        config.n_cells = int(self.n_cells.value())
        config.n_stages = int(self.n_stages.value())
        config.stage_shifts = [int(value.strip()) for value in self.stage_shifts.text().split(",") if value.strip()]
        config.boundary_base["temp"] = float(self.temperature.text())
        config.boundary_base["pressure"] = float(self.pressure.text())
        config.boundary_base["pH"] = float(self.ph.text())
        au_value = float(self.au.text())
        config.boundary_interpolation.setdefault("Au(3)", {"mode": "linear"})["start"] = au_value
        config.boundary_interpolation["Au(3)"]["end"] = au_value
        return config

    def load_config(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Load scenario config", "", "JSON (*.json)")
        if not filename:
            return
        self.config = ModelConfig.from_dict(json.loads(Path(filename).read_text(encoding="utf-8")))
        self._load_config_to_fields()
        self.status.setText(f"Loaded {filename}")

    def save_config(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Save scenario config", "scenario.json", "JSON (*.json)")
        if not filename:
            return
        config = self._fields_to_config()
        Path(filename).write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
        self.status.setText(f"Saved {filename}")

    def render_script(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Save PHREEQC script", "scenario.phr", "PHREEQC (*.phr)")
        if not filename:
            return
        script = build_phreeqc_script(self._fields_to_config())
        Path(filename).write_text(script, encoding="utf-8")
        self.status.setText(f"Rendered {filename}")

    def run_model(self) -> None:
        result = run_simulation(self._fields_to_config())
        output_dir = self.config.output_path
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "selected_output.csv"
        script_path = output_dir / "phreeqpyne_input.phr"
        script_path.write_text(result.script, encoding="utf-8")
        result.selected_output.to_csv(csv_path, index=False)
        QMessageBox.information(self, "Simulation complete", f"Wrote:\n{script_path}\n{csv_path}")
        self.status.setText("Simulation complete")


def main(argv: list[str] | None = None) -> int:
    app = QApplication(sys.argv if argv is None else argv)
    window = ScenarioEditor()
    window.show()
    return int(app.exec())
