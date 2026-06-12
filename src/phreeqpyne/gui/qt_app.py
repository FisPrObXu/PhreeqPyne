"""Qt-based interactive parameter editor for PhreeqPyne scenarios.

This module is optional and requires installing the ``gui`` extra.  It is not
imported by the package or CLI unless the user explicitly runs ``phreeqpyne gui``.
"""

from __future__ import annotations

import json
import sys
import traceback
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path

import pandas as pd
import matplotlib as mpl
import matplotlib.ticker as mticker
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMdiArea,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from phreeqpyne.config import ModelConfig, default_model_config
from phreeqpyne.phreeqc_blocks import build_rates_block, transform_progress
from phreeqpyne.phreeqc_builder import build_phreeqc_script
from phreeqpyne.runner import add_phase_percent_columns, run_simulation
from phreeqpyne.simulations import list_simulations


class FlexibleScrollArea(QScrollArea):
    """Scroll area that supports horizontal wheel gestures."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def wheelEvent(self, event) -> None:
        pixel_delta = event.pixelDelta()
        angle_delta = event.angleDelta()
        horizontal_delta = pixel_delta.x() or angle_delta.x()
        vertical_delta = pixel_delta.y() or angle_delta.y()
        wants_horizontal = bool(horizontal_delta) or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if wants_horizontal and self.horizontalScrollBar().maximum() > 0:
            delta = horizontal_delta or vertical_delta
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta)
            event.accept()
            return
        super().wheelEvent(event)


class PlotWindow(QMainWindow):
    """Independent window for Matplotlib output."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PhreeqPyne Plot")
        self.figure = Figure(figsize=(8, 5))
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCentralWidget(self.canvas)
        self.setMinimumSize(320, 240)
        self.resize(1000, 700)


class ScenarioEditor(QMainWindow):
    """Workflow-specific Qt window for editing one model family."""

    LINE_COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#7f7f7f"]
    STACK_FILL_COLORS = ["#9ecae1", "#fdae6b", "#a1d99b", "#c7b9d6", "#fdd0a2", "#9edae5", "#c49c94", "#c7c7c7"]
    STACK_LINE_COLORS = ["#1f77b4", "#e6550d", "#31a354", "#756bb1", "#fd8d3c", "#17becf", "#8c564b", "#636363"]

    def __init__(self, simulation_kind: str) -> None:
        super().__init__()
        self.config = default_model_config()
        self.simulation_kind_value = simulation_kind
        self.config.simulation_kind = simulation_kind
        self.stage_shift_fields: list[QSpinBox] = []
        self.boundary_base_fields: dict[str, QLineEdit] = {}
        self.boundary_rows: list[dict[str, object]] = []
        self.database_elements: list[str] = []
        self.gradient_rows: list[dict[str, object]] = []
        self.species_fields: dict[str, dict[str, QWidget]] = {}
        self.initial_solution_fields: dict[str, QLineEdit] = {}
        self.kinetics_fields: dict[str, QLineEdit] = {}
        self.transport_fields: dict[str, QLineEdit] = {}
        self.titration_fields: dict[str, QLineEdit] = {}
        self.rates_block_baseline = ""
        self.rates_block_loaded_custom = False
        self.plot_data: pd.DataFrame | None = None
        self.plot_window: PlotWindow | None = None
        self.plot_layers: list[dict[str, object]] = []
        self.setWindowTitle(f"PhreeqPyne {self.simulation_kind_value.title()} Editor")
        self.setMinimumSize(360, 280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._build_form()
        self._clear_startup_fields()

    def _build_form(self) -> None:
        root = QWidget(self)
        root.setMinimumSize(0, 0)
        root.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(root)
        self.simulation_workflows = list_simulations()
        self.simulation_kind = QComboBox()
        self.simulation_kind.addItem(self.simulation_kind_value)

        self.dll_path = QLineEdit()
        self.database_path = QLineEdit()
        self.output_dir = QLineEdit()
        self.n_cells = QSpinBox()
        self.n_cells.setRange(0, 10000)
        self.n_cells.setSpecialValueText("")
        self.n_stages = QSpinBox()
        self.n_stages.setRange(0, 1000)
        self.n_stages.setSpecialValueText("")
        self.n_stages.valueChanged.connect(self._sync_stage_shift_fields)
        self.stage_shift_grid = QWidget()
        self.stage_shift_layout = QGridLayout(self.stage_shift_grid)
        self.stage_shift_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget(root)
        self.tabs.addTab(self._scroll_tab(self._build_runtime_group()), "Runtime")
        if self.simulation_kind_value == "transport":
            self.tabs.addTab(self._scroll_tab(self._build_transport_group()), "Transport")
        if self.simulation_kind_value == "titration":
            self.tabs.addTab(self._scroll_tab(self._build_titration_group()), "Titration")
        self.tabs.addTab(self._scroll_tab(self._build_species_group()), self._solution_tab_title())
        if self.simulation_kind_value == "transport":
            self.tabs.addTab(self._scroll_tab(self._build_initial_solution_group()), "Initial")
            self.tabs.addTab(self._scroll_tab(self._build_kinetics_group()), "Kinetics")
        self.tabs.addTab(self._scroll_tab(self._build_plot_tab()), "Plot")
        layout.addWidget(self.tabs)

        browse_row = QHBoxLayout()
        config_load = QPushButton("Load config")
        config_load.setToolTip("Open a saved scenario JSON and fill this window with its values.")
        config_load.clicked.connect(self.load_config)
        config_save = QPushButton("Save config")
        config_save.setToolTip("Save all current window values as a scenario JSON.")
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

    def _clear_startup_fields(self) -> None:
        self._select_combo_text(self.simulation_kind, [self.simulation_kind_value])
        for field in [self.dll_path, self.database_path, self.output_dir]:
            field.clear()
        self.n_cells.setValue(0)
        self.n_stages.setValue(0)
        self._sync_stage_shift_fields()
        for field in self.transport_fields.values():
            field.clear()
        for field in self.titration_fields.values():
            field.clear()
        if hasattr(self, "titration_solution_source"):
            self.titration_solution_source.setCurrentIndex(-1)
        if hasattr(self, "titration_incremental"):
            self.titration_incremental.setCurrentIndex(-1)
        if hasattr(self, "boundary_left_condition"):
            self.boundary_left_condition.setCurrentIndex(-1)
        if hasattr(self, "boundary_right_condition"):
            self.boundary_right_condition.setCurrentIndex(-1)
        for field in self.boundary_base_fields.values():
            field.clear()
        self.clear_boundary_rows()
        self.database_elements = []
        for field in self.initial_solution_fields.values():
            field.clear()
        self.clear_gradient_rows()
        for field in self.kinetics_fields.values():
            field.clear()
        if hasattr(self, "rates_block"):
            self.rates_block.clear()
        self.rates_block_baseline = ""
        self.rates_block_loaded_custom = False
        self.plot_data = None
        self.plot_csv_path.clear()
        self.plot_stage.clear()
        self.plot_x_column.clear()
        self.plot_title.setText("PhreeqPyne selected output")
        self.plot_x_label.clear()
        self.plot_left_y_label.setText("Y axis 1")
        self.plot_right_y_label.setText("Y axis 2")
        self.plot_aspect_ratio.setText("auto")
        self.plot_y_axis_count.setValue(2)
        self.plot_stack_alpha.setText("0.75")
        self.plot_title_font_size.setText("14")
        self.plot_label_font_size.setText("11")
        self.plot_tick_font_size.setText("10")
        self.plot_legend_font_size.setText("10")
        self.plot_axis_line_width.setText("1.0")
        self.plot_tick_width.setText("1.0")
        self.plot_grid_color.setText("#b0b0b0")
        self.plot_grid_width.setText("0.8")
        self.plot_grid_alpha.setText("0.25")
        self.plot_figure_width.setText("8")
        self.plot_figure_height.setText("5")
        self.plot_legend_location.setCurrentText("outside upper right")
        self.plot_font_family.setCurrentText("Times New Roman")
        self.plot_grid_enabled.setCurrentText("on")
        self.plot_grid_axis.setCurrentText("both")
        self.plot_grid_style.setCurrentText("-")
        self.clear_plot_layers()
        self.status.setText("Blank case. Load a saved config or enter parameters.")

    def _scroll_tab(self, widget: QWidget) -> QScrollArea:
        scroll_area = FlexibleScrollArea(self)
        scroll_area.setWidget(widget)
        widget.setMinimumSize(0, 0)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return scroll_area

    def _build_runtime_group(self) -> QGroupBox:
        group = QGroupBox("Runtime paths")
        form = QFormLayout(group)
        form.addRow("Simulation workflow", QLabel(self.simulation_kind_value))
        form.addRow("IPhreeqc DLL/SO", self._path_row(self.dll_path, "file", "Select IPhreeqc DLL/SO"))
        form.addRow("Database", self._path_row(self.database_path, "file", "Select PHREEQC database"))
        form.addRow("Output directory", self._path_row(self.output_dir, "directory", "Select output directory"))
        return group

    def _build_transport_group(self) -> QGroupBox:
        group = QGroupBox("TRANSPORT controls")
        form = QFormLayout(group)
        form.addRow("Cells", self.n_cells)
        form.addRow("Stages", self.n_stages)
        form.addRow("Stage shifts", self.stage_shift_grid)
        for key in [
            "time_step",
            "flow_direction",
            "lengths",
            "dispersivities",
            "diffusion_coefficient",
            "correct_disp",
            "punch_cells",
            "punch_frequency",
        ]:
            field = QLineEdit()
            form.addRow(key, field)
            self.transport_fields[key] = field
        boundary_sides = ["constant", "closed", "flux"]
        self.boundary_left_condition = QComboBox()
        self.boundary_right_condition = QComboBox()
        self.boundary_left_condition.addItems(boundary_sides)
        self.boundary_right_condition.addItems(boundary_sides)
        condition_tip = (
            "PHREEQC TRANSPORT -boundary_conditions first last; each side can be constant, closed, or flux."
        )
        self.boundary_left_condition.setToolTip(condition_tip)
        self.boundary_right_condition.setToolTip(condition_tip)
        condition_row = QWidget(group)
        condition_layout = QHBoxLayout(condition_row)
        condition_layout.setContentsMargins(0, 0, 0, 0)
        condition_layout.addWidget(QLabel("first"))
        condition_layout.addWidget(self.boundary_left_condition)
        condition_layout.addWidget(QLabel("last"))
        condition_layout.addWidget(self.boundary_right_condition)
        form.addRow("boundary_conditions", condition_row)
        return group

    def _build_titration_group(self) -> QGroupBox:
        group = QGroupBox("Reaction-step titration controls")
        form = QFormLayout(group)
        self.titration_solution_source = QComboBox()
        self.titration_solution_source.setEditable(True)
        self.titration_solution_source.addItems(["reaction_solution"])
        self.titration_solution_source.setToolTip("Use the homogeneous reaction solution from the Reaction solution tab.")
        form.addRow("solution_source", self.titration_solution_source)
        for key in ["reaction_components", "reaction_total_moles", "reaction_steps"]:
            field = QLineEdit()
            self.titration_fields[key] = field
            form.addRow(key, field)
        self.titration_incremental = QComboBox()
        self.titration_incremental.addItems(["true", "false"])
        form.addRow("incremental_reactions", self.titration_incremental)
        hint = QLabel("reaction_components accepts entries like Hematite, 5e-7; separate multiple reactants with semicolons. PHREEQC equilibrates after each reaction step.")
        hint.setWordWrap(True)
        form.addRow("Format", hint)
        return group

    def _solution_tab_title(self) -> str:
        return "Reaction solution" if self.simulation_kind_value == "titration" else "Boundary"

    def _sync_stage_shift_fields(self) -> None:
        target_count = self.n_stages.value()
        current_values = [field.value() for field in self.stage_shift_fields]
        while self.stage_shift_layout.count():
            item = self.stage_shift_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.stage_shift_fields.clear()
        for index in range(target_count):
            label = QLabel(f"{index + 1}")
            field = QSpinBox()
            field.setRange(0, 1000000)
            default_value = current_values[index] if index < len(current_values) else 1
            field.setValue(default_value)
            row = index // 4
            col = (index % 4) * 2
            self.stage_shift_layout.addWidget(label, row, col)
            self.stage_shift_layout.addWidget(field, row, col + 1)
            self.stage_shift_fields.append(field)
        for boundary_row in getattr(self, "boundary_rows", []):
            self._refresh_boundary_row(boundary_row)

    def _path_row(self, line_edit: QLineEdit, selection_kind: str, title: str) -> QWidget:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        browse = QPushButton("Browse")
        browse.clicked.connect(lambda: self._browse_path(line_edit, selection_kind, title))
        layout.addWidget(line_edit)
        layout.addWidget(browse)
        return row

    def _browse_path(self, line_edit: QLineEdit, selection_kind: str, title: str) -> None:
        current_text = line_edit.text().strip()
        start_dir = current_text if current_text else ""
        if selection_kind == "directory":
            selected = QFileDialog.getExistingDirectory(self, title, start_dir)
        else:
            selected, _ = QFileDialog.getOpenFileName(self, title, start_dir, "All files (*)")
        if selected:
            line_edit.setText(selected)

    def _make_collapsible_card(self, title: str) -> tuple[QGroupBox, QPushButton, QWidget]:
        group = QGroupBox()
        outer_layout = QVBoxLayout(group)
        outer_layout.setContentsMargins(6, 6, 6, 6)
        header = QPushButton()
        header.setCheckable(True)
        header.setChecked(True)
        header.setProperty("card_title", title)
        header.setStyleSheet("QPushButton { text-align: left; font-weight: 600; padding: 4px 8px; }")
        content = QWidget(group)
        outer_layout.addWidget(header)
        outer_layout.addWidget(content)

        def toggle_content(checked: bool) -> None:
            content.setVisible(checked)
            header.setText(("[-] " if checked else "[+] ") + str(header.property("card_title")))

        header.toggled.connect(toggle_content)
        toggle_content(True)
        return group, header, content

    @staticmethod
    def _set_card_title(header: QPushButton, content: QWidget, title: str) -> None:
        header.setProperty("card_title", title)
        header.setText(("[-] " if content.isVisible() else "[+] ") + title)

    @staticmethod
    def _update_mode_shape_field(row: dict[str, object]) -> None:
        is_linear = row["mode"].currentText().lower() == "linear"
        row["shape_k"].setEnabled(not is_linear)
        row["shape_k"].setToolTip("Linear uses the original uncurved progress; shape_k is only used by exp/log modes.")

    def _build_species_group(self) -> QGroupBox:
        group = QGroupBox("Reaction solution" if self.simulation_kind_value == "titration" else "Boundary fluid")
        layout = QVBoxLayout(group)
        base_group = QGroupBox("Homogeneous solution" if self.simulation_kind_value == "titration" else "Fluid parameters")
        base_layout = QFormLayout(base_group)
        for key in ["temp", "pressure", "units", "pH", "pe", "water"]:
            field = QLineEdit()
            self.boundary_base_fields[key] = field
            base_layout.addRow(key, field)
        layout.addWidget(base_group)

        row_buttons = QHBoxLayout()
        add_component = QPushButton("Add component")
        add_component.clicked.connect(lambda: self.add_boundary_row())
        refresh_elements = QPushButton("Reload database elements")
        refresh_elements.clicked.connect(self.reload_database_elements)
        row_buttons.addWidget(add_component)
        row_buttons.addWidget(refresh_elements)
        layout.addLayout(row_buttons)

        self.boundary_rows_box = QGroupBox("Solution components")
        self.boundary_rows_layout = QVBoxLayout(self.boundary_rows_box)
        layout.addWidget(self.boundary_rows_box)

        if self.simulation_kind_value == "titration":
            hint = QLabel("Each component is a fixed concentration in one homogeneous reaction solution. No stage interpolation or cell gradient is used.")
        else:
            hint = QLabel("Rows with start/end values are stage-interpolated. Rows without start/end are written as constant boundary fluid components.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return group

    def reload_database_elements(self) -> None:
        self.database_elements = self._load_database_elements(self.database_path.text().strip())
        for row in self.boundary_rows:
            current = row["element"].currentText()
            row["element"].clear()
            row["element"].addItems(self.database_elements)
            row["element"].setEditable(True)
            self._select_combo_text(row["element"], [current])

    @staticmethod
    def _load_database_elements(database_path: str) -> list[str]:
        if not database_path or not Path(database_path).exists():
            return ["Na", "Cl", "K", "P(5)", "Cu(1)", "Cu(2)", "Fe(3)", "S(-2)", "Au(3)"]
        elements: list[str] = []
        in_master_species = False
        for raw_line in Path(database_path).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.upper().startswith("SOLUTION_MASTER_SPECIES"):
                in_master_species = True
                continue
            if in_master_species and line.upper().startswith("SOLUTION_SPECIES"):
                break
            if in_master_species and not line.startswith("#"):
                element = line.split()[0]
                if element not in elements:
                    elements.append(element)
        return elements or ["Na", "Cl", "K", "P(5)", "Cu(1)", "Cu(2)", "Fe(3)", "S(-2)", "Au(3)"]

    def add_boundary_row(self, element: str = "Na", base: object = "", spec: dict[str, object] | None = None) -> None:
        spec = spec or {}
        row_group, header, content = self._make_collapsible_card("Component")
        row_layout = QFormLayout()
        preview_figure = Figure(figsize=(2.4, 1.2))
        preview_canvas = FigureCanvas(preview_figure)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        controls = QWidget(content)
        controls.setLayout(row_layout)
        content_layout.addWidget(controls, 2)
        content_layout.addWidget(preview_canvas, 1)
        element_combo = QComboBox()
        element_combo.addItems(self.database_elements or self._load_database_elements(self.database_path.text().strip()))
        element_combo.setEditable(True)
        self._select_combo_text(element_combo, [element])
        base_value = QLineEdit("" if base is None else str(base))
        start = QLineEdit("" if "start" not in spec else str(spec.get("start", "")))
        end = QLineEdit("" if "end" not in spec else str(spec.get("end", "")))
        mode = QComboBox()
        mode.addItems(["linear", "exp", "log"])
        self._select_combo_text(mode, [str(spec.get("mode", "linear"))])
        shape_k = QLineEdit(str(spec.get("shape_k", 3.0)))
        remove = QPushButton("Remove")
        row = {
            "widget": row_group,
            "header": header,
            "content": content,
            "element": element_combo,
            "base": base_value,
            "start": start,
            "end": end,
            "mode": mode,
            "shape_k": shape_k,
            "preview_figure": preview_figure,
            "preview_canvas": preview_canvas,
        }
        remove.clicked.connect(lambda: self.remove_boundary_row(row))
        element_combo.currentTextChanged.connect(lambda: self._refresh_boundary_row(row))
        base_value.textChanged.connect(lambda: self._refresh_boundary_row(row))
        start.textChanged.connect(lambda: self._refresh_boundary_row(row))
        end.textChanged.connect(lambda: self._refresh_boundary_row(row))
        mode.currentTextChanged.connect(lambda: self._refresh_boundary_row(row))
        shape_k.textChanged.connect(lambda: self._refresh_boundary_row(row))
        row_layout.addRow("Element", element_combo)
        row_layout.addRow("Concentration", base_value)
        if self.simulation_kind_value == "transport":
            row_layout.addRow("Stage start", start)
            row_layout.addRow("Stage end", end)
            row_layout.addRow("Mode", mode)
            row_layout.addRow("Shape k", shape_k)
        row_layout.addRow("", remove)
        self.boundary_rows.append(row)
        self.boundary_rows_layout.addWidget(row_group)
        self._refresh_boundary_row(row)

    def remove_boundary_row(self, row: dict[str, object]) -> None:
        if row in self.boundary_rows:
            self.boundary_rows.remove(row)
        row["widget"].setParent(None)

    def _refresh_boundary_row(self, row: dict[str, object]) -> None:
        element = row["element"].currentText() or "unselected"
        self._set_card_title(row["header"], row["content"], f"Component: {element}")
        self._update_mode_shape_field(row)
        figure = row["preview_figure"]
        figure.clear()
        axis = figure.add_subplot(111)
        try:
            start_text = row["start"].text().strip()
            end_text = row["end"].text().strip()
            base_text = row["base"].text().strip()
            if self.simulation_kind_value == "titration":
                value = float(base_text) if base_text else 0.0
                axis.bar([element], [value], color="#0f766e", alpha=0.75)
                axis.set_ylabel("concentration", fontsize=7)
                axis.tick_params(labelsize=7)
                axis.grid(True, axis="y", alpha=0.25)
                figure.tight_layout(pad=0.4)
                row["preview_canvas"].draw_idle()
                return
            stages = max(1, self.n_stages.value())
            xs = list(range(1, stages + 1))
            if start_text or end_text:
                start = float(start_text)
                end = float(end_text)
                shape_k = float(row["shape_k"].text() or 0.0)
                ys = [
                    start
                    + (end - start)
                    * transform_progress(
                        progress=0.0 if stages == 1 else (stage - 1) / (stages - 1),
                        mode=row["mode"].currentText(),
                        shape_k=shape_k,
                    )
                    for stage in xs
                ]
            elif base_text:
                base = float(base_text)
                ys = [base for _ in xs]
            else:
                ys = [0.0 for _ in xs]
            axis.plot(xs, ys, color="#0f766e", linewidth=1.8, marker="o", markersize=2.5)
            axis.fill_between(xs, ys, min(ys), color="#99f6e4", alpha=0.35)
            axis.set_xlabel("stage", fontsize=7)
            axis.set_ylabel("value", fontsize=7)
            axis.tick_params(labelsize=7)
            axis.grid(True, alpha=0.25)
        except ValueError:
            axis.text(0.5, 0.5, "invalid", ha="center", va="center")
            axis.set_axis_off()
        figure.tight_layout(pad=0.4)
        row["preview_canvas"].draw_idle()

    def clear_boundary_rows(self) -> None:
        for row in self.boundary_rows:
            row["widget"].setParent(None)
        self.boundary_rows.clear()

    def _build_initial_solution_group(self) -> QGroupBox:
        group = QGroupBox("Initial pore solution")
        layout = QVBoxLayout(group)
        solution_group = QGroupBox("Solution composition")
        solution_layout = QFormLayout(solution_group)
        for key in ["temp", "pressure", "units", "pH", "pe", "Na", "Cl", "K", "P(5)", "Cu(2)", "Fe(3)", "S(-2)", "Au(3)", "water"]:
            field = QLineEdit()
            solution_layout.addRow(key, field)
            self.initial_solution_fields[key] = field
        layout.addWidget(solution_group)

        gradient_group = QGroupBox("Per-species gradients")
        gradient_layout = QVBoxLayout(gradient_group)
        gradient_buttons = QHBoxLayout()
        add_gradient = QPushButton("Add gradient species")
        add_gradient.clicked.connect(lambda: self.add_gradient_row())
        gradient_buttons.addWidget(add_gradient)
        gradient_buttons.addWidget(QLabel("Each row scales one species from shell cell to core cell."))
        gradient_layout.addLayout(gradient_buttons)
        self.gradient_rows_layout = QVBoxLayout()
        gradient_layout.addLayout(self.gradient_rows_layout)
        layout.addWidget(gradient_group)
        return group

    def add_gradient_row(
        self,
        species: str = "Na",
        mode: str = "linear",
        shape_k: object = 3.0,
        shell_factor: object = 1.0,
        core_factor: object = 0.1,
    ) -> None:
        row_group, header, content = self._make_collapsible_card("Gradient")
        controls = QWidget(content)
        row_layout = QFormLayout(controls)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(controls, 2)

        species_combo = QComboBox()
        species_combo.setEditable(True)
        species_combo.addItems([key for key in self.initial_solution_fields if key not in {"temp", "pressure", "units", "pH", "pe", "water"}])
        self._select_combo_text(species_combo, [species])
        mode_combo = QComboBox()
        mode_combo.addItems(["linear", "exp", "log"])
        self._select_combo_text(mode_combo, [str(mode).lower()])
        shape_field = QLineEdit(str(shape_k))
        shell_field = QLineEdit(str(shell_factor))
        core_field = QLineEdit(str(core_factor))
        remove = QPushButton("Remove")

        preview_figure = Figure(figsize=(2.4, 1.2))
        preview_canvas = FigureCanvas(preview_figure)
        content_layout.addWidget(preview_canvas, 1)

        row = {
            "widget": row_group,
            "header": header,
            "content": content,
            "species": species_combo,
            "mode": mode_combo,
            "shape_k": shape_field,
            "shell_factor": shell_field,
            "core_factor": core_field,
            "preview_figure": preview_figure,
            "preview_canvas": preview_canvas,
        }
        remove.clicked.connect(lambda: self.remove_gradient_row(row))
        species_combo.currentTextChanged.connect(lambda: self._refresh_gradient_row(row))
        mode_combo.currentTextChanged.connect(lambda: self._refresh_gradient_row(row))
        shape_field.textChanged.connect(lambda: self._refresh_gradient_row(row))
        shell_field.textChanged.connect(lambda: self._refresh_gradient_row(row))
        core_field.textChanged.connect(lambda: self._refresh_gradient_row(row))
        row_layout.addRow("Species", species_combo)
        row_layout.addRow("Mode", mode_combo)
        row_layout.addRow("Shape k", shape_field)
        row_layout.addRow("Shell factor", shell_field)
        row_layout.addRow("Core factor", core_field)
        row_layout.addRow("", remove)
        self.gradient_rows.append(row)
        self.gradient_rows_layout.addWidget(row_group)
        self._refresh_gradient_row(row)

    def remove_gradient_row(self, row: dict[str, object]) -> None:
        if row in self.gradient_rows:
            self.gradient_rows.remove(row)
        row["widget"].setParent(None)

    def clear_gradient_rows(self) -> None:
        for row in self.gradient_rows:
            row["widget"].setParent(None)
        self.gradient_rows.clear()

    def _refresh_gradient_row(self, row: dict[str, object]) -> None:
        species = row["species"].currentText() or "unselected"
        self._set_card_title(row["header"], row["content"], f"Gradient: {species}")
        self._update_mode_shape_field(row)
        figure = row["preview_figure"]
        figure.clear()
        axis = figure.add_subplot(111)
        try:
            shape_k = float(row["shape_k"].text() or 0.0)
            shell_factor = float(row["shell_factor"].text() or 1.0)
            core_factor = float(row["core_factor"].text() or shell_factor)
            xs = [index / 50 for index in range(51)]
            ys = [
                shell_factor
                + (core_factor - shell_factor)
                * transform_progress(progress=x, mode=row["mode"].currentText(), shape_k=shape_k)
                for x in xs
            ]
            axis.plot(xs, ys, color="#2563eb", linewidth=1.8)
            axis.fill_between(xs, ys, min(ys), color="#93c5fd", alpha=0.35)
            axis.set_xlabel("cell progress", fontsize=7)
            axis.set_ylabel("factor", fontsize=7)
            axis.tick_params(labelsize=7)
            axis.grid(True, alpha=0.25)
        except ValueError:
            axis.text(0.5, 0.5, "invalid", ha="center", va="center")
            axis.set_axis_off()
        figure.tight_layout(pad=0.4)
        row["preview_canvas"].draw_idle()

    def _load_gradient_rows(self, gradient_cfg: dict[str, object]) -> None:
        species_cfg = gradient_cfg.get("species", [])
        if isinstance(species_cfg, dict):
            for species, spec in species_cfg.items():
                spec = spec if isinstance(spec, dict) else {}
                self.add_gradient_row(
                    species=str(species),
                    mode=str(spec.get("mode", gradient_cfg.get("mode", "linear"))),
                    shape_k=spec.get("shape_k", gradient_cfg.get("shape_k", 3.0)),
                    shell_factor=spec.get("shell_factor", gradient_cfg.get("shell_factor", 1.0)),
                    core_factor=spec.get("core_factor", gradient_cfg.get("core_factor", 0.1)),
                )
            return
        for species in species_cfg:
            self.add_gradient_row(
                species=str(species),
                mode=str(gradient_cfg.get("mode", "linear")),
                shape_k=gradient_cfg.get("shape_k", 3.0),
                shell_factor=gradient_cfg.get("shell_factor", 1.0),
                core_factor=gradient_cfg.get("core_factor", 0.1),
            )

    def _gradient_rows_to_config(self) -> dict[str, dict[str, float | str]]:
        species_config: dict[str, dict[str, float | str]] = {}
        for row in self.gradient_rows:
            species = row["species"].currentText().strip()
            if not species:
                continue
            mode = row["mode"].currentText()
            species_config[species] = {
                "mode": mode,
                "shape_k": 0.0 if mode == "linear" else float(row["shape_k"].text() or 3.0),
                "shell_factor": float(row["shell_factor"].text() or 1.0),
                "core_factor": float(row["core_factor"].text() or 1.0),
            }
        return species_config

    def _build_kinetics_group(self) -> QGroupBox:
        group = QGroupBox("Kinetics")
        layout = QFormLayout(group)
        hint = QLabel(
            "Generic PHREEQC KINETICS controls. Use rate_name, formula, amounts, and solver controls for the kinetic reactant; edit the RATES block for a custom rate law."
        )
        hint.setWordWrap(True)
        layout.addRow("Description", hint)
        for key in [
            "rate_name",
            "formula",
            "m0",
            "m",
            "affinity_factor",
            "sp_area",
            "roughness",
            "lgkH",
            "e_H",
            "nH",
            "lgkH2O",
            "e_H2O",
            "lgkOH",
            "e_OH",
            "nOH",
            "tol",
            "step_divide",
            "runge_kutta",
            "bad_step_max",
        ]:
            field = QLineEdit()
            layout.addRow(key, field)
            self.kinetics_fields[key] = field
        self.rates_block = QTextEdit()
        self.rates_block.setMinimumHeight(220)
        self.rates_block.setToolTip("Optional custom PHREEQC RATES block for the rate_name above.")
        layout.addRow("RATES block", self.rates_block)
        return group

    def _build_plot_tab(self) -> QWidget:
        tab = QWidget(self)
        tab.setMinimumSize(0, 0)
        tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(tab)

        controls = QGroupBox("Plot controls")
        form = QFormLayout(controls)
        self.plot_csv_path = QLineEdit()
        form.addRow("CSV", self._path_row(self.plot_csv_path, "file", "Select selected_output.csv"))
        self.plot_stage = QComboBox()
        self.plot_x_column = QComboBox()
        self.plot_title = QLineEdit("PhreeqPyne selected output")
        self.plot_x_label = QLineEdit()
        self.plot_left_y_label = QLineEdit("Stack area")
        self.plot_right_y_label = QLineEdit("Line")
        self.plot_aspect_ratio = QLineEdit("auto")
        self.plot_y_axis_count = QSpinBox()
        self.plot_y_axis_count.setRange(1, 12)
        self.plot_y_axis_count.setValue(2)
        self.plot_y_axis_count.valueChanged.connect(self._sync_plot_y_axis_options)
        if self.simulation_kind_value == "transport":
            form.addRow("Stage", self.plot_stage)
        form.addRow("X column", self.plot_x_column)
        form.addRow("Title", self.plot_title)
        form.addRow("X label", self.plot_x_label)
        form.addRow("Left Y label", self.plot_left_y_label)
        form.addRow("Right Y label", self.plot_right_y_label)
        form.addRow("Y axes", self.plot_y_axis_count)
        form.addRow("Aspect ratio", self.plot_aspect_ratio)
        layout.addWidget(controls)

        style_group, _, style_content = self._make_collapsible_card("Plot style / axes settings")
        style_form = QFormLayout(style_content)
        self.plot_stack_alpha = QLineEdit("0.75")
        self.plot_legend_location = QComboBox()
        self.plot_legend_location.addItems(["outside upper right", "outside upper left", "outside lower right", "outside lower left"])
        self.plot_font_family = QComboBox()
        self.plot_font_family.addItems(["Times New Roman", "Arial", "Helvetica", "Calibri", "Cambria", "Georgia"])
        self.plot_title_font_size = QLineEdit("14")
        self.plot_label_font_size = QLineEdit("11")
        self.plot_tick_font_size = QLineEdit("10")
        self.plot_legend_font_size = QLineEdit("10")
        self.plot_axis_line_width = QLineEdit("1.0")
        self.plot_tick_width = QLineEdit("1.0")
        self.plot_grid_enabled = QComboBox()
        self.plot_grid_enabled.addItems(["on", "off"])
        self.plot_grid_axis = QComboBox()
        self.plot_grid_axis.addItems(["both", "x", "y"])
        self.plot_grid_style = QComboBox()
        self.plot_grid_style.addItems(["-", "--", "-.", ":"])
        self.plot_grid_color = QLineEdit("#b0b0b0")
        self.plot_grid_width = QLineEdit("0.8")
        self.plot_grid_alpha = QLineEdit("0.25")
        self.plot_figure_width = QLineEdit("8")
        self.plot_figure_height = QLineEdit("5")
        style_form.addRow("Fill alpha", self.plot_stack_alpha)
        style_form.addRow("Legend", self.plot_legend_location)
        style_form.addRow("Font family", self.plot_font_family)
        style_form.addRow("Title size", self.plot_title_font_size)
        style_form.addRow("Axis label size", self.plot_label_font_size)
        style_form.addRow("Tick size", self.plot_tick_font_size)
        style_form.addRow("Legend size", self.plot_legend_font_size)
        style_form.addRow("Axis line width", self.plot_axis_line_width)
        style_form.addRow("Tick width", self.plot_tick_width)
        style_form.addRow("Grid", self.plot_grid_enabled)
        style_form.addRow("Grid axis", self.plot_grid_axis)
        style_form.addRow("Grid style", self.plot_grid_style)
        style_form.addRow("Grid color", self._color_row(self.plot_grid_color))
        style_form.addRow("Grid width", self.plot_grid_width)
        style_form.addRow("Grid alpha", self.plot_grid_alpha)
        style_form.addRow("Figure width", self.plot_figure_width)
        style_form.addRow("Figure height", self.plot_figure_height)
        layout.addWidget(style_group)

        self.plot_layers_box = QGroupBox("Y layers")
        self.plot_layers_layout = QVBoxLayout(self.plot_layers_box)
        layer_buttons = QHBoxLayout()
        add_line = QPushButton("Add line")
        add_line.clicked.connect(lambda: self.add_plot_layer("line"))
        add_stack = QPushButton("Add stack area")
        add_stack.clicked.connect(lambda: self.add_plot_layer("stack"))
        clear_layers = QPushButton("Clear layers")
        clear_layers.clicked.connect(self.clear_plot_layers)
        layer_buttons.addWidget(add_line)
        layer_buttons.addWidget(add_stack)
        layer_buttons.addWidget(clear_layers)
        self.plot_layers_layout.addLayout(layer_buttons)
        layer_scroll = FlexibleScrollArea(tab)
        layer_scroll.setWidget(self.plot_layers_box)
        layer_scroll.setMinimumHeight(220)
        layer_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(layer_scroll)

        button_row = QHBoxLayout()
        load_button = QPushButton("Load CSV")
        load_button.clicked.connect(self.load_plot_csv)
        current_button = QPushButton("Load current output")
        current_button.clicked.connect(self.load_current_output_plot)
        draw_button = QPushButton("Draw / Refresh")
        draw_button.clicked.connect(self.draw_plot)
        open_button = QPushButton("Open plot window")
        open_button.clicked.connect(self.open_plot_window)
        save_button = QPushButton("Save figure")
        save_button.clicked.connect(self.save_plot)
        button_row.addWidget(load_button)
        button_row.addWidget(current_button)
        button_row.addWidget(draw_button)
        if self.simulation_kind_value == "transport":
            draw_all_stages = QPushButton("Draw all stages")
            draw_all_stages.clicked.connect(self.draw_all_stages_plot)
            button_row.addWidget(draw_all_stages)
        button_row.addWidget(open_button)
        button_row.addWidget(save_button)
        layout.addLayout(button_row)

        if self.simulation_kind_value == "titration":
            hint = QLabel("Choose a reaction-step X column, then assign each output series to one of the Y axes. Stack layers use axis 1.")
        else:
            hint = QLabel("Choose one X column, set the total Y axes, then assign each line layer to axis 1, 2, 3, or higher. Stack layers use axis 1.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return tab

    def _color_row(self, line_edit: QLineEdit) -> QWidget:
        row = QWidget(self)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        choose = QPushButton("Choose")
        choose.clicked.connect(lambda: self.choose_color(line_edit))
        layout.addWidget(line_edit)
        layout.addWidget(choose)
        return row

    def add_plot_layer(self, layer_type: str = "line") -> None:
        layer = self._make_plot_layer(layer_type)
        self.plot_layers.append(layer)
        self.plot_layers_layout.addWidget(layer["widget"])
        self._refresh_plot_layer_title(layer)

    def clear_plot_layers(self) -> None:
        for layer in self.plot_layers:
            layer["widget"].setParent(None)
        self.plot_layers.clear()

    def _make_plot_layer(self, layer_type: str) -> dict[str, object]:
        group, header, content = self._make_collapsible_card("Line layer" if layer_type == "line" else "Stack area layer")
        group.setToolTip("Click the header button to expand or collapse this plotting layer.")
        layout = QFormLayout(content)
        plot_type = QComboBox()
        plot_type.addItems(["line", "stack"])
        plot_type.setCurrentText(layer_type)
        y_column = QComboBox()
        if self.plot_data is not None:
            y_column.addItems(self._plot_y_columns_for_type(layer_type))
        label = QLineEdit()
        line_default, fill_default = self._default_layer_colors(layer_type)
        line_color = QLineEdit(line_default)
        fill_color = QLineEdit(fill_default)
        line_style = QComboBox()
        line_style.addItems(["-", "--", "-.", ":"])
        line_width = QLineEdit("1.5")
        y_axis = QComboBox()
        y_axis.addItems(self._plot_y_axis_labels())
        if layer_type == "line":
            self._select_combo_text(y_axis, ["2", "1"])
        y_axis.setEnabled(layer_type == "line")
        remove = QPushButton("Remove")
        layer: dict[str, object] = {
            "widget": group,
            "header": header,
            "content": content,
            "type": plot_type,
            "y": y_column,
            "label": label,
            "line_color": line_color,
            "fill_color": fill_color,
            "line_style": line_style,
            "line_width": line_width,
            "y_axis": y_axis,
        }
        remove.clicked.connect(lambda: self.remove_plot_layer(layer))
        plot_type.currentTextChanged.connect(lambda: self._handle_layer_type_changed(layer))
        y_column.currentTextChanged.connect(lambda: self._handle_layer_changed(layer))
        y_axis.currentTextChanged.connect(lambda: self._handle_layer_changed(layer))
        layout.addRow("Type", plot_type)
        layout.addRow("Y column", y_column)
        layout.addRow("Label", label)
        layout.addRow("Line color", self._color_row(line_color))
        layout.addRow("Fill color", self._color_row(fill_color))
        layout.addRow("Line style", line_style)
        layout.addRow("Line width", line_width)
        layout.addRow("Y axis", y_axis)
        layout.addRow("", remove)
        return layer

    def remove_plot_layer(self, layer: dict[str, object]) -> None:
        if layer in self.plot_layers:
            self.plot_layers.remove(layer)
        layer["widget"].setParent(None)

    def _refresh_plot_layer_title(self, layer: dict[str, object]) -> None:
        self._set_card_title(layer["header"], layer["content"], self._plot_layer_title(layer))

    def _handle_layer_changed(self, layer: dict[str, object]) -> None:
        self._refresh_plot_layer_title(layer)

    def _handle_layer_type_changed(self, layer: dict[str, object]) -> None:
        self._refresh_layer_y_options(layer)
        line_color, fill_color = self._default_layer_colors(layer["type"].currentText(), exclude_layer=layer)
        layer["line_color"].setText(line_color)
        layer["fill_color"].setText(fill_color)
        layer["y_axis"].setEnabled(layer["type"].currentText() == "line")
        if layer["type"].currentText() == "line":
            self._select_combo_text(layer["y_axis"], ["2", "1"])
        else:
            layer["y_axis"].setCurrentText("1")
        self._handle_layer_changed(layer)

    def _redraw_plot_if_ready(self) -> None:
        return

    @staticmethod
    def _plot_layer_title(layer: dict[str, object]) -> str:
        plot_type = layer["type"].currentText()
        y_column = layer["y"].currentText() or "unselected"
        axis_suffix = f" axis {layer['y_axis'].currentText()}" if plot_type == "line" else ""
        return f"{plot_type}: {y_column}{axis_suffix}"

    def _plot_y_axis_labels(self) -> list[str]:
        return [str(index) for index in range(1, self.plot_y_axis_count.value() + 1)]

    def _sync_plot_y_axis_options(self) -> None:
        labels = self._plot_y_axis_labels()
        for layer in self.plot_layers:
            combo = layer["y_axis"]
            current_text = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(labels)
            if current_text in labels:
                combo.setCurrentText(current_text)
            elif layer["type"].currentText() == "line":
                combo.setCurrentText("2" if "2" in labels else "1")
            else:
                combo.setCurrentText("1")
            combo.blockSignals(False)
            self._refresh_plot_layer_title(layer)

    def _default_layer_colors(self, layer_type: str, exclude_layer: dict[str, object] | None = None) -> tuple[str, str]:
        layer_index = self._plot_layer_type_count(layer_type, exclude_layer=exclude_layer)
        if layer_type == "stack":
            fill_color = self.STACK_FILL_COLORS[layer_index % len(self.STACK_FILL_COLORS)]
            line_color = self.STACK_LINE_COLORS[layer_index % len(self.STACK_LINE_COLORS)]
            return line_color, fill_color
        line_color = self.LINE_COLORS[layer_index % len(self.LINE_COLORS)]
        return line_color, line_color

    def _plot_layer_type_count(self, layer_type: str, exclude_layer: dict[str, object] | None = None) -> int:
        count = 0
        for layer in self.plot_layers:
            if layer is exclude_layer:
                continue
            if layer["type"].currentText() == layer_type:
                count += 1
        return count

    def _load_config_to_fields(self) -> None:
        self.config.simulation_kind = self.simulation_kind_value
        self._select_combo_text(self.simulation_kind, [self.simulation_kind_value])
        self.dll_path.setText(self.config.runtime.dll_path)
        self.database_path.setText(self.config.runtime.database_path)
        self.output_dir.setText(self.config.runtime.output_dir)
        self.n_cells.setValue(self.config.n_cells)
        self.n_stages.setValue(self.config.n_stages)
        self._sync_stage_shift_fields()
        for field, value in zip(self.stage_shift_fields, self.config.stage_shifts, strict=False):
            field.setValue(int(value))
        for key, field in self.transport_fields.items():
            value = self.config.transport_params.get(key)
            field.setText("" if value is None else str(value))
        if self.titration_fields:
            titration_params = self.config.titration_params
            self._set_combo_text_or_add(self.titration_solution_source, str(titration_params.get("solution_source", "boundary")))
            self.titration_fields["reaction_components"].setText(
                self._format_reaction_components(titration_params.get("reaction_components", []))
            )
            self.titration_fields["reaction_total_moles"].setText(str(titration_params.get("reaction_total_moles", 1.0)))
            self.titration_fields["reaction_steps"].setText(str(titration_params.get("reaction_steps", 1000)))
            self._set_combo_text_or_add(
                self.titration_incremental,
                "true" if bool(titration_params.get("incremental_reactions", True)) else "false",
            )
        if hasattr(self, "boundary_left_condition") and hasattr(self, "boundary_right_condition"):
            boundary_condition = str(self.config.transport_params.get("boundary_conditions", "constant closed"))
            condition_parts = boundary_condition.split()
            first_condition = condition_parts[0] if condition_parts else "constant"
            last_condition = condition_parts[1] if len(condition_parts) > 1 else "closed"
            self._select_combo_text(self.boundary_left_condition, [first_condition])
            self._select_combo_text(self.boundary_right_condition, [last_condition])
        for key, field in self.boundary_base_fields.items():
            field.setText(str(self.config.boundary_base.get(key, "")))
        self.database_elements = self._load_database_elements(self.config.runtime.database_path)
        self.clear_boundary_rows()
        reserved_boundary_keys = {"temp", "pressure", "units", "pH", "pe", "water"}
        for key, value in self.config.boundary_base.items():
            if key not in reserved_boundary_keys:
                self.add_boundary_row(key, base=value)
        if self.simulation_kind_value == "transport":
            for key, spec in self.config.boundary_interpolation.items():
                self.add_boundary_row(key, spec=spec)
        for key, field in self.initial_solution_fields.items():
            field.setText(str(self.config.initial_pore_solution.get(key, "")))
        if hasattr(self, "gradient_rows_layout"):
            self.clear_gradient_rows()
            self._load_gradient_rows(self.config.initial_pore_gradient)
        for key, field in self.kinetics_fields.items():
            field.setText(str(self.config.hematite_kinetics.get(key, "")))
        if hasattr(self, "rates_block"):
            self.rates_block_loaded_custom = bool(str(self.config.hematite_kinetics.get("rates_block", "")).strip())
            self.rates_block_baseline = build_rates_block(self.config.hematite_kinetics)
            self.rates_block.setPlainText(self.rates_block_baseline)
        self._load_plot_config_to_fields(self.config.plot)

    def _fields_to_config(self) -> ModelConfig:
        config = self.config
        config.simulation_kind = self.simulation_kind_value
        config.runtime.dll_path = self.dll_path.text().strip()
        config.runtime.database_path = self.database_path.text().strip()
        config.runtime.output_dir = self.output_dir.text().strip() or "."
        config.n_cells = int(self.n_cells.value())
        config.n_stages = int(self.n_stages.value())
        config.stage_shifts = [field.value() for field in self.stage_shift_fields]
        for key, field in self.boundary_base_fields.items():
            value = self._parse_solution_value(field.text())
            config.boundary_base[key] = value
        for key, field in self.transport_fields.items():
            text = field.text().strip()
            if key in {"flow_direction", "boundary_conditions", "punch_cells"}:
                config.transport_params[key] = text or None
            elif key == "correct_disp":
                config.transport_params[key] = self._parse_optional_bool(text)
            elif key == "punch_frequency":
                config.transport_params[key] = int(text)
            else:
                config.transport_params[key] = None if text == "" else float(text)
        if hasattr(self, "boundary_left_condition") and hasattr(self, "boundary_right_condition"):
            config.transport_params["boundary_conditions"] = (
                f"{self.boundary_left_condition.currentText()} {self.boundary_right_condition.currentText()}"
            )
        if self.titration_fields:
            config.titration_params = {
                "solution_source": self.titration_solution_source.currentText().strip() or "boundary",
                "reaction_components": self._parse_reaction_components(
                    self.titration_fields["reaction_components"].text()
                ),
                "reaction_total_moles": float(self.titration_fields["reaction_total_moles"].text() or 1.0),
                "reaction_steps": int(self.titration_fields["reaction_steps"].text() or 1000),
                "incremental_reactions": self.titration_incremental.currentText().lower() != "false",
            }
        reserved_boundary_keys = {"temp", "pressure", "units", "pH", "pe", "water"}
        config.boundary_base = {key: config.boundary_base[key] for key in reserved_boundary_keys if key in config.boundary_base}
        config.boundary_interpolation = {}
        for row in self.boundary_rows:
            element = row["element"].currentText().strip()
            if not element:
                continue
            start_text = row["start"].text().strip()
            end_text = row["end"].text().strip()
            if self.simulation_kind_value == "transport" and (start_text or end_text):
                mode = row["mode"].currentText()
                config.boundary_interpolation[element] = {
                    "start": float(start_text),
                    "end": float(end_text),
                    "mode": mode,
                    "shape_k": 0.0 if mode == "linear" else float(row["shape_k"].text() or 3.0),
                }
            elif row["base"].text().strip():
                config.boundary_base[element] = self._parse_solution_value(row["base"].text())
        config.initial_pore_solution = {
            key: self._parse_solution_value(field.text())
            for key, field in self.initial_solution_fields.items()
            if field.text().strip()
        }
        config.initial_pore_gradient = {"species": self._gradient_rows_to_config()}
        for key, field in self.kinetics_fields.items():
            text = field.text().strip()
            if key in {"rate_name", "formula"}:
                config.hematite_kinetics[key] = text
            elif key in {"step_divide", "runge_kutta", "bad_step_max"}:
                config.hematite_kinetics[key] = int(text)
            else:
                config.hematite_kinetics[key] = float(text)
        if hasattr(self, "rates_block"):
            rates_text = self.rates_block.toPlainText().strip()
            if rates_text and (self.rates_block_loaded_custom or rates_text != self.rates_block_baseline.strip()):
                config.hematite_kinetics["rates_block"] = rates_text
            else:
                config.hematite_kinetics.pop("rates_block", None)
        config.plot = self._fields_to_plot_config(config.plot)
        return config

    @staticmethod
    def _format_reaction_components(components: object) -> str:
        if not isinstance(components, list):
            return ""
        lines = []
        for component in components:
            if isinstance(component, (list, tuple)) and len(component) == 2:
                lines.append(f"{component[0]}, {component[1]}")
        return "; ".join(lines)

    @staticmethod
    def _parse_reaction_components(text: str) -> list[tuple[str, float]]:
        components: list[tuple[str, float]] = []
        for raw_part in re.split(r"[;\n]+", text):
            part = raw_part.strip()
            if not part:
                continue
            if "," in part:
                name, amount = part.split(",", 1)
            else:
                pieces = part.split()
                if len(pieces) < 2:
                    raise ValueError(f"Invalid reaction component: {part}")
                name = " ".join(pieces[:-1])
                amount = pieces[-1]
            components.append((name.strip(), float(amount.strip())))
        return components or [("Hematite", 5e-7)]

    def _fields_to_plot_config(self, existing_plot_config: dict[str, object] | None = None) -> dict[str, object]:
        plot_config = dict(existing_plot_config or {})
        plot_config.update(
            {
                "csv_path": self.plot_csv_path.text().strip(),
                "stage": self.plot_stage.currentText(),
                "x_column": self.plot_x_column.currentText(),
                "title": self.plot_title.text(),
                "x_label": self.plot_x_label.text(),
                "left_y_label": self.plot_left_y_label.text(),
                "right_y_label": self.plot_right_y_label.text(),
                "y_axis_count": self.plot_y_axis_count.value(),
                "aspect_ratio": self.plot_aspect_ratio.text(),
                "stack_alpha": self.plot_stack_alpha.text(),
                "legend_location": self.plot_legend_location.currentText(),
                "font_family": self.plot_font_family.currentText(),
                "title_font_size": self.plot_title_font_size.text(),
                "label_font_size": self.plot_label_font_size.text(),
                "tick_font_size": self.plot_tick_font_size.text(),
                "legend_font_size": self.plot_legend_font_size.text(),
                "axis_line_width": self.plot_axis_line_width.text(),
                "tick_width": self.plot_tick_width.text(),
                "grid_enabled": self.plot_grid_enabled.currentText(),
                "grid_axis": self.plot_grid_axis.currentText(),
                "grid_style": self.plot_grid_style.currentText(),
                "grid_color": self.plot_grid_color.text(),
                "grid_width": self.plot_grid_width.text(),
                "grid_alpha": self.plot_grid_alpha.text(),
                "figure_width": self.plot_figure_width.text(),
                "figure_height": self.plot_figure_height.text(),
                "layers": [self._plot_layer_to_config(layer) for layer in self.plot_layers],
            }
        )
        return plot_config

    def _load_plot_config_to_fields(self, plot_config: dict[str, object] | None) -> None:
        if not plot_config:
            return
        csv_path = str(plot_config.get("csv_path", "") or plot_config.get("plot_csv_path", "")).strip()
        self.plot_csv_path.setText(csv_path)
        if csv_path and Path(csv_path).exists():
            self._load_plot_csv(Path(csv_path))
        self._set_combo_text_or_add(self.plot_stage, str(plot_config.get("stage", "")))
        self._set_combo_text_or_add(self.plot_x_column, str(plot_config.get("x_column", "")))
        self.plot_title.setText(str(plot_config.get("title", self.plot_title.text())))
        self.plot_x_label.setText(str(plot_config.get("x_label", self.plot_x_label.text())))
        self.plot_left_y_label.setText(str(plot_config.get("left_y_label", self.plot_left_y_label.text())))
        self.plot_right_y_label.setText(str(plot_config.get("right_y_label", self.plot_right_y_label.text())))
        self.plot_y_axis_count.setValue(int(plot_config.get("y_axis_count", self.plot_y_axis_count.value()) or 2))
        self.plot_aspect_ratio.setText(str(plot_config.get("aspect_ratio", self.plot_aspect_ratio.text())))
        self.plot_stack_alpha.setText(str(plot_config.get("stack_alpha", self.plot_stack_alpha.text())))
        self._set_combo_text_or_add(self.plot_legend_location, str(plot_config.get("legend_location", "")))
        self._set_combo_text_or_add(self.plot_font_family, str(plot_config.get("font_family", "")))
        self.plot_title_font_size.setText(str(plot_config.get("title_font_size", self.plot_title_font_size.text())))
        self.plot_label_font_size.setText(str(plot_config.get("label_font_size", self.plot_label_font_size.text())))
        self.plot_tick_font_size.setText(str(plot_config.get("tick_font_size", self.plot_tick_font_size.text())))
        self.plot_legend_font_size.setText(str(plot_config.get("legend_font_size", self.plot_legend_font_size.text())))
        self.plot_axis_line_width.setText(str(plot_config.get("axis_line_width", self.plot_axis_line_width.text())))
        self.plot_tick_width.setText(str(plot_config.get("tick_width", self.plot_tick_width.text())))
        self._set_combo_text_or_add(self.plot_grid_enabled, str(plot_config.get("grid_enabled", "")))
        self._set_combo_text_or_add(self.plot_grid_axis, str(plot_config.get("grid_axis", "")))
        self._set_combo_text_or_add(self.plot_grid_style, str(plot_config.get("grid_style", "")))
        self.plot_grid_color.setText(str(plot_config.get("grid_color", self.plot_grid_color.text())))
        self.plot_grid_width.setText(str(plot_config.get("grid_width", self.plot_grid_width.text())))
        self.plot_grid_alpha.setText(str(plot_config.get("grid_alpha", self.plot_grid_alpha.text())))
        self.plot_figure_width.setText(str(plot_config.get("figure_width", self.plot_figure_width.text())))
        self.plot_figure_height.setText(str(plot_config.get("figure_height", self.plot_figure_height.text())))
        layer_configs = plot_config.get("layers", [])
        if isinstance(layer_configs, list):
            self.clear_plot_layers()
            for layer_config in layer_configs:
                if isinstance(layer_config, dict):
                    self._add_plot_layer_from_config(layer_config)

    @staticmethod
    def _plot_layer_to_config(layer: dict[str, object]) -> dict[str, object]:
        return {
            "type": layer["type"].currentText(),
            "y": layer["y"].currentText(),
            "label": layer["label"].text(),
            "line_color": layer["line_color"].text(),
            "fill_color": layer["fill_color"].text(),
            "line_style": layer["line_style"].currentText(),
            "line_width": layer["line_width"].text(),
            "y_axis": layer["y_axis"].currentText(),
        }

    def _add_plot_layer_from_config(self, layer_config: dict[str, object]) -> None:
        self.add_plot_layer(str(layer_config.get("type", "line") or "line"))
        layer = self.plot_layers[-1]
        self._set_combo_text_or_add(layer["type"], str(layer_config.get("type", "line")))
        self._refresh_layer_y_options(layer)
        self._set_combo_text_or_add(layer["y"], str(layer_config.get("y", "")))
        layer["label"].setText(str(layer_config.get("label", "")))
        layer["line_color"].setText(str(layer_config.get("line_color", layer["line_color"].text())))
        layer["fill_color"].setText(str(layer_config.get("fill_color", layer["fill_color"].text())))
        self._set_combo_text_or_add(layer["line_style"], str(layer_config.get("line_style", "")))
        layer["line_width"].setText(str(layer_config.get("line_width", layer["line_width"].text())))
        axis_label = self._normalize_plot_y_axis(layer_config.get("y_axis", "2"))
        if axis_label.isdigit() and int(axis_label) > self.plot_y_axis_count.value():
            self.plot_y_axis_count.setValue(int(axis_label))
        self._set_combo_text_or_add(layer["y_axis"], axis_label)
        layer["y_axis"].setEnabled(layer["type"].currentText() == "line")
        self._refresh_plot_layer_title(layer)

    @staticmethod
    def _normalize_plot_y_axis(value: object) -> str:
        text = str(value).strip().lower()
        if text == "dedicated":
            return "3"
        if text == "shared":
            return "2"
        return text or "2"

    @staticmethod
    def _set_combo_text_or_add(combo: QComboBox, text: str) -> None:
        if not text:
            return
        index = combo.findText(text)
        if index < 0:
            combo.addItem(text)
            index = combo.findText(text)
        combo.setCurrentIndex(index)

    @staticmethod
    def _parse_solution_value(text: str) -> str | float:
        stripped = text.strip()
        try:
            return float(stripped)
        except ValueError:
            return stripped

    @staticmethod
    def _parse_optional_bool(text: str) -> bool | None:
        normalized = text.strip().lower()
        if normalized in {"", "none", "null"}:
            return None
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        raise ValueError(f"Invalid boolean value: {text}")

    def choose_color(self, line_edit: QLineEdit) -> None:
        color = QColorDialog.getColor()
        if color.isValid():
            line_edit.setText(color.name())

    def load_plot_csv(self) -> None:
        try:
            filename = self.plot_csv_path.text().strip()
            if not filename:
                filename, _ = QFileDialog.getOpenFileName(self, "Load selected output", "", "CSV (*.csv)")
            if not filename:
                return
            self._load_plot_csv(Path(filename))
            self.status.setText(f"Loaded plot data: {filename}")
        except Exception as exc:
            self._show_error("Load plot CSV failed", exc)

    def load_current_output_plot(self) -> None:
        try:
            csv_path = self._fields_to_config().output_path / "selected_output.csv"
            self._load_plot_csv(csv_path)
            self.status.setText(f"Loaded current output: {csv_path}")
        except Exception as exc:
            self._show_error("Load current output failed", exc)

    def _load_plot_csv(self, csv_path: Path) -> None:
        self.plot_data = pd.read_csv(csv_path)
        if self.simulation_kind.currentText() == "transport":
            self._add_cell_plot_column()
        self.plot_data = add_phase_percent_columns(self.plot_data)
        self.plot_csv_path.setText(str(csv_path))
        columns = [str(column) for column in self.plot_data.columns]
        self.plot_stage.clear()
        if "stage" in self.plot_data.columns:
            stages = sorted(
                value
                for value in pd.to_numeric(self.plot_data["stage"], errors="coerce").dropna().unique()
                if value != -99
            )
            self.plot_stage.addItems([str(int(value)) if float(value).is_integer() else str(value) for value in stages])
        else:
            self.plot_stage.addItem("all")
        self.plot_x_column.clear()
        self.plot_x_column.addItems(columns)
        if self.simulation_kind.currentText() == "titration":
            self._select_combo_text(self.plot_x_column, ["rxn_step", "step", "time_days", "time"])
        else:
            self._select_combo_text(self.plot_x_column, ["cell", "soln", "solution", "dist_x", "dist", "time_days", "time", "step"])
        for layer in self.plot_layers:
            self._refresh_layer_y_options(layer)
        if not self.plot_layers:
            self.add_plot_layer("line")
            self._select_combo_text(self.plot_layers[0]["y"], ["pH", "Au(mol/kgw)", "Au(3)(mol/kgw)", "Cu(mol/kgw)"])
        self.status.setText("Plot data loaded. Click Draw / Refresh to update the figure.")

    def _plot_y_columns_for_type(self, layer_type: str) -> list[str]:
        if self.plot_data is None:
            return []
        columns = [str(column) for column in self.plot_data.columns]
        if layer_type == "stack":
            return [column for column in columns if column.endswith("_pct")]
        return columns

    def _refresh_layer_y_options(self, layer: dict[str, object]) -> None:
        y_combo = layer["y"]
        current_text = y_combo.currentText()
        layer_type = layer["type"].currentText()
        y_combo.blockSignals(True)
        y_combo.clear()
        y_combo.addItems(self._plot_y_columns_for_type(layer_type))
        if current_text:
            self._select_combo_text(y_combo, [current_text])
        if y_combo.currentIndex() < 0 and y_combo.count() > 0:
            y_combo.setCurrentIndex(0)
        y_combo.blockSignals(False)
        self._refresh_plot_layer_title(layer)

    def _add_cell_plot_column(self) -> None:
        if self.plot_data is None or "cell" in self.plot_data.columns:
            return
        for candidate in ["soln", "solution"]:
            if candidate in self.plot_data.columns:
                self.plot_data["cell"] = pd.to_numeric(self.plot_data[candidate], errors="coerce")
                return

    @staticmethod
    def _select_combo_text(combo: QComboBox, candidates: list[str]) -> None:
        for candidate in candidates:
            index = combo.findText(candidate)
            if index >= 0:
                combo.setCurrentIndex(index)
                return

    def draw_plot(self) -> None:
        try:
            if self.plot_data is None:
                raise ValueError("No CSV data loaded.")
            x_column = self.plot_x_column.currentText()
            layers = self._active_plot_layers()
            if not x_column:
                raise ValueError("Choose an X column.")
            if not layers:
                raise ValueError("Add at least one Y layer.")

            stage_value = self.plot_stage.currentText()
            plot_frame = self._filtered_plot_data(x_column, [layer["y"] for layer in layers], stage_value)
            self._ensure_plot_window()
            figure = self.plot_window.figure
            figure.clear()
            style = self._plot_style()
            self._apply_figure_size(figure, style)
            ax_left = figure.add_subplot(111)
            legend_items = self._plot_frame_on_axes(ax_left, plot_frame, x_column, layers, stage_value, style, show_title=True)
            self._place_figure_legend(figure, legend_items, style)
            self._adjust_figure_margins(figure, style)
            self.plot_window.canvas.draw()
            self.plot_window.show()
            self.plot_window.raise_()
            removed_count = len(self.plot_data) - len(plot_frame)
            if self.simulation_kind_value == "transport":
                self.status.setText(f"Plot refreshed for stage {stage_value}; filtered {removed_count} rows")
            else:
                self.status.setText(f"Titration plot refreshed; filtered {removed_count} rows")
        except Exception as exc:
            self._show_error("Draw plot failed", exc)

    def draw_all_stages_plot(self) -> None:
        if self.simulation_kind_value != "transport":
            self.status.setText("All-stage plotting is only available for transport simulations.")
            return
        try:
            if self.plot_data is None:
                raise ValueError("No CSV data loaded.")
            x_column = self.plot_x_column.currentText()
            layers = self._active_plot_layers()
            if not x_column:
                raise ValueError("Choose an X column.")
            if not layers:
                raise ValueError("Add at least one Y layer.")
            stage_values = [self.plot_stage.itemText(index) for index in range(self.plot_stage.count())]
            stage_values = [stage for stage in stage_values if stage and stage != "all"] or ["all"]
            self._ensure_plot_window()
            figure = self.plot_window.figure
            figure.clear()
            style = self._plot_style()
            width = float(style["figure_width"])
            height = max(float(style["figure_height"]), 2.6 * len(stage_values))
            figure.set_size_inches(width, height, forward=True)
            axes = figure.subplots(len(stage_values), 1, squeeze=False)
            shared_legend_items: tuple[list[object], list[str]] = ([], [])
            stage_frames = [
                (
                    stage_value,
                    self._filtered_plot_data(x_column, [layer["y"] for layer in layers], stage_value),
                )
                for stage_value in stage_values
            ]
            for index, stage_value in enumerate(stage_values):
                ax_left = axes[index][0]
                plot_frame = stage_frames[index][1]
                legend_items = self._plot_frame_on_axes(
                    ax_left,
                    plot_frame,
                    x_column,
                    layers,
                    stage_value,
                    style,
                    show_title=index == 0,
                    title_suffix=f"stage {stage_value}",
                    show_x_label=index == len(stage_values) - 1,
                )
                if index == 0:
                    shared_legend_items = legend_items
                if index < len(stage_values) - 1:
                    ax_left.tick_params(labelbottom=False)
                    ax_left.set_xlabel("")
            self._place_figure_legend(figure, shared_legend_items, style)
            self._adjust_figure_margins(figure, style, multi_stage=True)
            self.plot_window.canvas.draw()
            self.plot_window.show()
            self.plot_window.raise_()
            self.status.setText(f"Plot refreshed for all {len(stage_values)} stages")
        except Exception as exc:
            self._show_error("Draw all stages failed", exc)

    def _plot_frame_on_axes(
        self,
        ax_left,
        plot_frame: pd.DataFrame,
        x_column: str,
        layers: list[dict[str, object]],
        stage_value: str,
        style: dict[str, object],
        show_title: bool,
        title_suffix: str | None = None,
        show_x_label: bool = True,
    ) -> tuple[list[object], list[str]]:
        if plot_frame.empty:
            if self.simulation_kind_value == "transport":
                raise ValueError(f"No plottable rows for stage {stage_value}.")
            raise ValueError("No plottable titration rows.")
        stack_layers = [layer for layer in layers if layer["type"] == "stack"]
        line_layers = [layer for layer in layers if layer["type"] == "line"]
        axis_map = {1: ax_left}

        if stack_layers:
            stack_values = [plot_frame[layer["y"]] for layer in stack_layers]
            stack_labels = [layer["label"] or layer["y"] for layer in stack_layers]
            fill_colors = [layer["fill_color"] for layer in stack_layers]
            ax_left.stackplot(
                plot_frame[x_column],
                stack_values,
                labels=stack_labels,
                colors=fill_colors,
                alpha=float(style["fill_alpha"]),
            )
            cumulative = None
            for values, layer in zip(stack_values, stack_layers, strict=True):
                cumulative = values if cumulative is None else cumulative + values
                ax_left.plot(
                    plot_frame[x_column],
                    cumulative,
                    color=layer["line_color"],
                    linestyle=layer["line_style"],
                    linewidth=layer["line_width"],
                )
            ax_left.set_ylim(0, 100)

        for axis_number in sorted({self._layer_y_axis_number(layer) for layer in line_layers}):
            if axis_number == 1:
                continue
            axis = ax_left.twinx()
            if axis_number > 2:
                axis.spines["right"].set_position(("axes", 1.0 + 0.09 * (axis_number - 2)))
            axis.spines["right"].set_visible(True)
            axis_map[axis_number] = axis

        for layer in line_layers:
            axis_number = self._layer_y_axis_number(layer)
            axis = axis_map.get(axis_number, ax_left)
            axis.plot(
                plot_frame[x_column],
                plot_frame[layer["y"]],
                color=layer["line_color"],
                linestyle=layer["line_style"],
                linewidth=layer["line_width"],
                label=layer["label"] or layer["y"],
            )

        for axis_number, axis in axis_map.items():
            axis_layers = [layer for layer in line_layers if self._layer_y_axis_number(layer) == axis_number]
            if axis_number <= 2:
                continue
            if len(axis_layers) == 1:
                color = axis_layers[0]["line_color"]
                axis_label = axis_layers[0]["label"] or axis_layers[0]["y"]
                axis.set_ylabel(axis_label, fontsize=float(style["label_size"]), fontfamily=str(style["font_family"]), color=color)
                axis.tick_params(axis="y", colors=color)
                axis.spines["right"].set_color(color)
            else:
                axis.set_ylabel(f"Y axis {axis_number}", fontsize=float(style["label_size"]), fontfamily=str(style["font_family"]))

        title = self.plot_title.text()
        if title_suffix:
            title = f"{title} - {title_suffix}"
        if show_title:
            ax_left.set_title(title, fontsize=float(style["title_size"]), fontfamily=str(style["font_family"]))
        else:
            subtitle = f"stage {stage_value}" if self.simulation_kind_value == "transport" else "reaction steps"
            ax_left.set_title(subtitle, fontsize=float(style["label_size"]), fontfamily=str(style["font_family"]))
        ax_left.set_xlabel(
            (self.plot_x_label.text() or x_column) if show_x_label else "",
            fontsize=float(style["label_size"]),
            fontfamily=str(style["font_family"]),
        )
        ax_left.set_ylabel(self.plot_left_y_label.text(), fontsize=float(style["label_size"]), fontfamily=str(style["font_family"]))
        if 2 in axis_map:
            axis_map[2].set_ylabel(self.plot_right_y_label.text(), fontsize=float(style["label_size"]), fontfamily=str(style["font_family"]))
        aspect_ratio = self._parse_aspect_ratio(self.plot_aspect_ratio.text())
        if aspect_ratio == "equal":
            ax_left.set_aspect("equal", adjustable="box")
        self._apply_grid_style(ax_left, style)
        for axis in axis_map.values():
            self._apply_axis_style(axis, style)
            self._apply_y_axis_format(axis, style)
        self._set_tight_x_limits(ax_left, plot_frame[x_column])
        for axis in axis_map.values():
            if axis is not ax_left:
                self._set_tight_x_limits(axis, plot_frame[x_column])
        return self._legend_items(ax_left, list(axis_map.values()))

    @staticmethod
    def _layer_y_axis_number(layer: dict[str, object]) -> int:
        try:
            return max(1, int(str(layer.get("y_axis", "2"))))
        except ValueError:
            return 2

    def _plot_style(self) -> dict[str, object]:
        return {
            "fill_alpha": float(self.plot_stack_alpha.text() or 0.75),
            "legend_location": self.plot_legend_location.currentText(),
            "font_family": self.plot_font_family.currentText() or "Times New Roman",
            "title_size": float(self.plot_title_font_size.text() or 14),
            "label_size": float(self.plot_label_font_size.text() or 11),
            "tick_size": float(self.plot_tick_font_size.text() or 10),
            "legend_size": float(self.plot_legend_font_size.text() or 10),
            "axis_line_width": float(self.plot_axis_line_width.text() or 1.0),
            "tick_width": float(self.plot_tick_width.text() or 1.0),
            "grid_enabled": self.plot_grid_enabled.currentText() == "on",
            "grid_axis": self.plot_grid_axis.currentText(),
            "grid_style": self.plot_grid_style.currentText(),
            "grid_color": self.plot_grid_color.text().strip() or "#b0b0b0",
            "grid_width": float(self.plot_grid_width.text() or 0.8),
            "grid_alpha": float(self.plot_grid_alpha.text() or 0.25),
            "figure_width": float(self.plot_figure_width.text() or 8),
            "figure_height": float(self.plot_figure_height.text() or 5),
        }

    def _apply_figure_size(self, figure: Figure, style: dict[str, object]) -> None:
        width = float(style["figure_width"])
        height = float(style["figure_height"])
        aspect_ratio = self._parse_aspect_ratio(self.plot_aspect_ratio.text())
        if isinstance(aspect_ratio, float):
            height = width / aspect_ratio
        figure.set_size_inches(width, height, forward=True)

    @staticmethod
    def _apply_axis_style(axis, style: dict[str, object]) -> None:
        for spine in axis.spines.values():
            spine.set_linewidth(float(style["axis_line_width"]))
        axis.tick_params(
            direction="in",
            width=float(style["tick_width"]),
            labelsize=float(style["tick_size"]),
            top=True,
            right=True,
        )
        for label in [*axis.get_xticklabels(), *axis.get_yticklabels()]:
            label.set_fontfamily(str(style["font_family"]))

    @staticmethod
    def _apply_y_axis_format(axis, style: dict[str, object]) -> None:
        formatter = mticker.ScalarFormatter(useMathText=True)
        formatter.set_useOffset(False)
        formatter.set_scientific(True)
        formatter.set_powerlimits((-4, 4))
        axis.yaxis.set_major_formatter(formatter)
        axis.yaxis.set_major_locator(mticker.MaxNLocator(nbins=4))
        axis.yaxis.offsetText.set_fontsize(float(style["tick_size"]))
        axis.yaxis.offsetText.set_fontfamily(str(style["font_family"]))

    @staticmethod
    def _apply_grid_style(axis, style: dict[str, object]) -> None:
        axis.grid(
            bool(style["grid_enabled"]),
            axis=str(style["grid_axis"]),
            linestyle=str(style["grid_style"]),
            color=str(style["grid_color"]),
            linewidth=float(style["grid_width"]),
            alpha=float(style["grid_alpha"]),
        )

    @staticmethod
    def _set_tight_x_limits(axis, x_values: pd.Series) -> None:
        numeric = pd.to_numeric(x_values, errors="coerce").dropna()
        if numeric.empty:
            return
        axis.margins(x=0)
        x_min = float(numeric.min())
        x_max = float(numeric.max())
        if x_min == x_max:
            axis.set_xlim(x_min - 0.5, x_max + 0.5)
        else:
            axis.set_xlim(x_min, x_max)

    @staticmethod
    def _legend_anchor(location: str) -> tuple[str, tuple[float, float]]:
        mapping = {
            "outside upper right": ("upper left", (0.77, 0.93)),
            "outside upper left": ("upper right", (0.23, 0.93)),
            "outside lower right": ("lower left", (0.77, 0.16)),
            "outside lower left": ("lower right", (0.23, 0.16)),
        }
        return mapping.get(location, mapping["outside upper right"])

    @staticmethod
    def _legend_items(ax_left, line_axes) -> tuple[list[object], list[str]]:
        handles_left, labels_left = ax_left.get_legend_handles_labels()
        handles = list(handles_left)
        labels = list(labels_left)
        for axis in line_axes:
            if axis is ax_left:
                continue
            axis_handles, axis_labels = axis.get_legend_handles_labels()
            handles.extend(axis_handles)
            labels.extend(axis_labels)
        return handles, labels

    def _place_figure_legend(
        self,
        figure: Figure,
        legend_items: tuple[list[object], list[str]],
        style: dict[str, object],
    ) -> None:
        handles, labels = legend_items
        if not handles:
            return
        loc, anchor = self._legend_anchor(str(style["legend_location"]))
        legend = figure.legend(
            handles,
            labels,
            loc=loc,
            bbox_to_anchor=anchor,
            bbox_transform=figure.transFigure,
            borderaxespad=0.2,
            fontsize=float(style["legend_size"]),
            frameon=True,
        )
        for text in legend.get_texts():
            text.set_fontfamily(str(style["font_family"]))

    @staticmethod
    def _adjust_figure_margins(figure: Figure, style: dict[str, object], multi_stage: bool = False) -> None:
        location = str(style["legend_location"])
        left = 0.1
        right = 0.9
        bottom = 0.12 if not multi_stage else 0.07
        top = 0.9 if not multi_stage else 0.94
        if "right" in location:
            right = 0.68
        if "left" in location:
            left = 0.32
        if "lower" in location:
            bottom = max(bottom, 0.24)
        if "upper" in location:
            top = min(top, 0.82 if not multi_stage else 0.86)
        max_right_spine = 1.0
        for axis in figure.axes:
            position = axis.spines["right"].get_position()
            if isinstance(position, tuple) and position[0] == "axes":
                max_right_spine = max(max_right_spine, float(position[1]))
        if max_right_spine > 1.0:
            extra_axes_width = max_right_spine - 1.0
            right = min(right, max(0.5, 0.9 - extra_axes_width))
        figure.subplots_adjust(left=left, right=right, top=top, bottom=bottom, hspace=0.34 if multi_stage else 0.2)

    def _active_plot_layers(self) -> list[dict[str, object]]:
        layers: list[dict[str, object]] = []
        for layer in self.plot_layers:
            y_column = layer["y"].currentText()
            if not y_column:
                continue
            layers.append(
                {
                    "type": layer["type"].currentText(),
                    "y": y_column,
                    "label": layer["label"].text().strip(),
                    "line_color": layer["line_color"].text().strip() or "#1f77b4",
                    "fill_color": layer["fill_color"].text().strip() or "#9ecae1",
                    "line_style": layer["line_style"].currentText(),
                    "line_width": float(layer["line_width"].text()),
                    "y_axis": layer["y_axis"].currentText(),
                }
            )
        return layers

    def _filtered_plot_data(self, x_column: str, y_columns: list[str], stage_value: str) -> pd.DataFrame:
        if self.plot_data is None:
            raise ValueError("No CSV data loaded.")
        helper_columns = ["step_global", "step", "time", "time_days"]
        available_helpers = [column for column in helper_columns if column in self.plot_data.columns]
        columns = list(dict.fromkeys([x_column, *y_columns, *available_helpers]))
        frame = self.plot_data.copy()
        if stage_value and stage_value != "all" and "stage" in frame.columns:
            stage_numeric = pd.to_numeric(frame["stage"], errors="coerce")
            selected_stage = float(stage_value)
            frame = frame[stage_numeric == selected_stage]
        frame = frame[columns].copy()
        for column in columns:
            numeric = pd.to_numeric(frame[column], errors="coerce")
            frame = frame[numeric.notna() & (numeric != -99)]
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if x_column == "cell":
            frame = frame[frame["cell"] > 0]
            sort_columns = ["cell", *available_helpers]
            frame = frame.sort_values(sort_columns)
            frame = frame.groupby("cell", as_index=False).tail(1)
            frame = frame.sort_values("cell")
        return frame[list(dict.fromkeys([x_column, *y_columns]))]

    def _ensure_plot_window(self) -> None:
        if self.plot_window is None:
            self.plot_window = PlotWindow(self)

    @staticmethod
    def _parse_aspect_ratio(text: str) -> str | float | None:
        normalized = text.strip().lower()
        if normalized in {"", "auto", "none"}:
            return None
        if normalized == "equal":
            return "equal"
        if ":" in normalized:
            width, height = normalized.split(":", 1)
            return float(width) / float(height)
        return float(normalized)

    def open_plot_window(self) -> None:
        try:
            self._ensure_plot_window()
            self.plot_window.show()
            self.plot_window.raise_()
            if self.plot_data is not None:
                self.draw_plot()
        except Exception as exc:
            self._show_error("Open plot window failed", exc)

    def save_plot(self) -> None:
        try:
            self._ensure_plot_window()
            filename, _ = QFileDialog.getSaveFileName(self, "Save figure", "selected_output_plot.png", "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
            if not filename:
                return
            if Path(filename).suffix.lower() == ".svg":
                mpl.rcParams["svg.fonttype"] = "none"
            self.plot_window.figure.savefig(filename, dpi=200, bbox_inches="tight")
            self.status.setText(f"Saved figure: {filename}")
        except Exception as exc:
            self._show_error("Save figure failed", exc)

    def load_config(self) -> None:
        try:
            filename, _ = QFileDialog.getOpenFileName(self, "Load scenario config", "", "JSON (*.json)")
            if not filename:
                return
            loaded_config = ModelConfig.from_dict(json.loads(Path(filename).read_text(encoding="utf-8")))
            if loaded_config.simulation_kind != self.simulation_kind_value:
                raise ValueError(
                    f"This is a {self.simulation_kind_value} window; open {loaded_config.simulation_kind} configs in their own window."
                )
            self.config = loaded_config
            self._load_config_to_fields()
            self.status.setText(f"Loaded {filename}; edit fields, then save/render/run.")
        except Exception as exc:
            self._show_error("Load config failed", exc)

    def save_config(self) -> None:
        try:
            filename, _ = QFileDialog.getSaveFileName(self, "Save scenario config", "scenario.json", "JSON (*.json)")
            if not filename:
                return
            config = self._fields_to_config()
            Path(filename).write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
            self.status.setText(f"Saved {filename}")
        except Exception as exc:
            self._show_error("Save config failed", exc)

    def render_script(self) -> None:
        try:
            filename, _ = QFileDialog.getSaveFileName(self, "Save PHREEQC script", "scenario.phr", "PHREEQC (*.phr)")
            if not filename:
                return
            script = build_phreeqc_script(self._fields_to_config())
            Path(filename).write_text(script, encoding="utf-8")
            self.status.setText(f"Rendered {filename}")
        except Exception as exc:
            self._show_error("Render script failed", exc)

    def run_model(self) -> None:
        try:
            config = deepcopy(self._fields_to_config())
            script_path, csv_path = self._run_config_to_output(config, config.output_path)
            self._load_plot_csv(csv_path)
            QMessageBox.information(self, "Simulation complete", f"Wrote:\n{script_path}\n{csv_path}")
            self.status.setText("Simulation complete")
        except Exception as exc:
            self._show_error("Run simulation failed", exc)

    def run_transport_and_titration(self) -> None:
        try:
            base_config = deepcopy(self._fields_to_config())
            base_output_dir = base_config.output_path
            configs: list[tuple[str, ModelConfig, Path]] = []
            for kind in ["transport", "titration"]:
                config = deepcopy(base_config)
                config.simulation_kind = kind
                config.runtime.output_dir = str(base_output_dir / kind)
                configs.append((kind, config, Path(config.runtime.output_dir)))

            outputs: dict[str, tuple[Path, Path]] = {}
            self.status.setText("Running transport and titration...")
            QApplication.processEvents()
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {
                    executor.submit(self._run_config_to_output, config, output_dir): kind
                    for kind, config, output_dir in configs
                }
                for future in as_completed(futures):
                    kind = futures[future]
                    outputs[kind] = future.result()

            titration_csv = outputs["titration"][1]
            self._load_plot_csv(titration_csv)
            details = "\n".join(
                f"{kind}:\n{script_path}\n{csv_path}"
                for kind, (script_path, csv_path) in outputs.items()
            )
            QMessageBox.information(self, "Parallel simulations complete", f"Wrote:\n{details}")
            self.status.setText("Transport and titration complete")
        except Exception as exc:
            self._show_error("Parallel simulations failed", exc)

    @staticmethod
    def _run_config_to_output(config: ModelConfig, output_dir: Path) -> tuple[Path, Path]:
        result = run_simulation(config)
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "selected_output.csv"
        script_path = output_dir / "phreeqpyne_input.phr"
        script_path.write_text(result.script, encoding="utf-8")
        result.selected_output.to_csv(csv_path, index=False)
        return script_path, csv_path

    def _show_error(self, title: str, exc: Exception) -> None:
        details = traceback.format_exc()
        QMessageBox.critical(self, title, f"{exc}\n\nDetails:\n{details}")
        self.status.setText(title)


class MainControlWindow(QMainWindow):
    """Main GUI workspace that owns internal simulation editor windows."""

    def __init__(self) -> None:
        super().__init__()
        self.transport_window: ScenarioEditor | None = None
        self.titration_window: ScenarioEditor | None = None
        self.editor_subwindows: dict[str, object] = {}
        self.setWindowTitle("PhreeqPyne Workspace")
        self.setMinimumSize(900, 620)
        self._build_form()

    def _build_form(self) -> None:
        root = QWidget(self)
        layout = QVBoxLayout(root)
        layout.addWidget(QLabel("Open simulation tools as internal workspace windows; close tools when they are not needed."))

        toolbar_row = QHBoxLayout()
        self.tools_combo = QComboBox()
        self.tools_combo.addItems(["", "Transport", "Titration"])
        self.tools_combo.activated.connect(self.open_selected_tool)
        run_both = QPushButton("Run Open Transport + Titration")
        run_both.clicked.connect(self.run_open_editors)
        tile_windows = QPushButton("Tile")
        tile_windows.clicked.connect(lambda: self.mdi_area.tileSubWindows())
        cascade_windows = QPushButton("Cascade")
        cascade_windows.clicked.connect(lambda: self.mdi_area.cascadeSubWindows())
        toolbar_row.addWidget(QLabel("Tools"))
        toolbar_row.addWidget(self.tools_combo)
        toolbar_row.addWidget(run_both)
        toolbar_row.addWidget(tile_windows)
        toolbar_row.addWidget(cascade_windows)
        toolbar_row.addStretch(1)
        layout.addLayout(toolbar_row)

        self.mdi_area = QMdiArea(root)
        self.mdi_area.setTabsClosable(True)
        self.mdi_area.setTabsMovable(True)
        self.mdi_area.setViewMode(QMdiArea.ViewMode.TabbedView)
        layout.addWidget(self.mdi_area, 1)

        self.status = QLabel("Ready")
        layout.addWidget(self.status)
        self.setCentralWidget(root)

    def open_selected_tool(self, index: int) -> None:
        tool_name = self.tools_combo.itemText(index).lower()
        if tool_name in {"transport", "titration"}:
            self.open_editor(tool_name)
        self.tools_combo.setCurrentIndex(0)

    def open_editor(self, simulation_kind: str) -> ScenarioEditor:
        current = self._editor_for_kind(simulation_kind)
        if current is None:
            current = ScenarioEditor(simulation_kind)
            current.setWindowFlags(Qt.WindowType.Widget)
            subwindow = self.mdi_area.addSubWindow(current, Qt.WindowType.FramelessWindowHint)
            subwindow.setWindowTitle(current.windowTitle())
            subwindow.setWindowFlags(Qt.WindowType.FramelessWindowHint)
            subwindow.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            subwindow.destroyed.connect(lambda _=None, kind=simulation_kind: self._clear_editor_reference(kind))
            self.editor_subwindows[simulation_kind] = subwindow
            self._set_editor_for_kind(simulation_kind, current)
            subwindow.show()
        subwindow = self.editor_subwindows.get(simulation_kind)
        if subwindow is not None:
            self.mdi_area.setActiveSubWindow(subwindow)
            subwindow.show()
            subwindow.raise_()
        self.status.setText(f"{simulation_kind.title()} window open")
        return current

    def close_editor(self, simulation_kind: str) -> None:
        subwindow = self.editor_subwindows.get(simulation_kind)
        if subwindow is not None:
            subwindow.close()
        self._clear_editor_reference(simulation_kind)
        self.status.setText(f"{simulation_kind.title()} window closed")

    def run_open_editors(self) -> None:
        try:
            transport = self.open_editor("transport")
            titration = self.open_editor("titration")
            configs = [
                ("transport", deepcopy(transport._fields_to_config())),
                ("titration", deepcopy(titration._fields_to_config())),
            ]
            base_output_dir = configs[0][1].output_path
            self.status.setText("Running open transport and titration windows...")
            QApplication.processEvents()
            outputs: dict[str, tuple[Path, Path]] = {}
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {}
                for kind, config in configs:
                    config.runtime.output_dir = str(base_output_dir / kind)
                    futures[executor.submit(ScenarioEditor._run_config_to_output, config, Path(config.runtime.output_dir))] = kind
                for future in as_completed(futures):
                    outputs[futures[future]] = future.result()
            details = "\n".join(
                f"{kind}:\n{script_path}\n{csv_path}"
                for kind, (script_path, csv_path) in sorted(outputs.items())
            )
            QMessageBox.information(self, "Parallel simulations complete", f"Wrote:\n{details}")
            self.status.setText("Parallel simulations complete")
        except Exception as exc:
            details = traceback.format_exc()
            QMessageBox.critical(self, "Parallel simulations failed", f"{exc}\n\nDetails:\n{details}")
            self.status.setText("Parallel simulations failed")

    def _editor_for_kind(self, simulation_kind: str) -> ScenarioEditor | None:
        if simulation_kind == "transport":
            return self.transport_window
        if simulation_kind == "titration":
            return self.titration_window
        raise ValueError(f"Unknown editor kind: {simulation_kind}")

    def _set_editor_for_kind(self, simulation_kind: str, editor: ScenarioEditor) -> None:
        if simulation_kind == "transport":
            self.transport_window = editor
        elif simulation_kind == "titration":
            self.titration_window = editor
        else:
            raise ValueError(f"Unknown editor kind: {simulation_kind}")

    def _clear_editor_reference(self, simulation_kind: str) -> None:
        if simulation_kind == "transport":
            self.transport_window = None
        elif simulation_kind == "titration":
            self.titration_window = None
        self.editor_subwindows.pop(simulation_kind, None)


def main(argv: list[str] | None = None) -> int:
    app = QApplication(sys.argv if argv is None else argv)
    window = MainControlWindow()
    window.show()
    return int(app.exec())
