# PhreeqPyne

Building a handful simulation paradigm for hydrothermal water-rock simulation using PhreeqPy with multi-programming language.

## Project-level direction

`CFAS_therm_240C_Ccp_SCM_multistage.ipynb` remains the exploratory notebook, while reusable logic is being migrated into the `phreeqpyne` Python package. The package currently provides:

- typed, serializable model/runtime configuration;
- staged boundary-fluid interpolation;
- PHREEQC input-script generation through an extensible simulation workflow registry;
- the current `transport` workflow and a `titration` batch-reaction workflow;
- an optional Qt scenario editor for window-based parameter entry;
- a runtime wrapper that imports PhreeqPy only when a simulation is executed;
- a CLI for writing default configs, rendering `.phr` input files, and running IPhreeqc.

See [`docs/applicationization_guide.md`](docs/applicationization_guide.md) for the Chinese roadmap from notebook prototype to project-level application.

## Quick start

Install the package in editable mode:

```bash
python -m pip install -e .[dev]
```

Write a default scenario config:

```bash
phreeqpyne init-config --output scenario.json
```

Render the PHREEQC script without requiring IPhreeqc to be installed:

```bash
phreeqpyne build-script --config scenario.json --output scenario.phr
```

List registered simulation workflows:

```bash
phreeqpyne list-simulations
```

Open the optional Qt parameter-entry window after installing the GUI extra:

```bash
python -m pip install -e .[gui]
phreeqpyne gui
```

The GUI opens a main workspace that behaves like a tabbed internal-window
browser. Use the `Tools` dropdown to open or activate `transport` and
`titration` editors; close unneeded tools from their internal tab close button.
Editors can also be tiled or cascaded inside the workspace. Each editor owns
only the tabs for its simulation family. Choose a separate working folder for
each tool before opening it; generated configs, rendered PHREEQC scripts, and
simulation outputs default to that tool's folder. Titration uses one homogeneous reaction
solution and reaction-step output, so it does not expose transport stages,
all-stage plotting, shell-to-core gradients, or kinetic-rate controls. The Plot tab can load
`selected_output.csv`; plots open in a separate window and can be redrawn after
changing columns, grouping, line style, line width, color, titles, axis labels,
and aspect ratio. The main workspace also includes a one-click run for the
currently open transport and titration editor configurations, writing them to
separate output folders.
Titration reactants may be constant (`Hematite, 5e-7`) or step-scheduled
(`Hematite, 5e-7 -> 1e-7; Chalcopyrite(alpha), 0 -> 4e-7`), which generates
sequential reaction blocks that reuse the previous step's solution and
equilibrium phases.
Use the `Equilibrium phases` tab to set mineral precipitation capacity and
redox/fugacity buffers such as `O2(g)`.
For stepwise mineral inventory, set titration `mode` to `inventory_step`; the
configured component schedule is written as sequential `EQUILIBRIUM_PHASES`
additions that reuse the previous step's saved solution and phase assemblage.
The Titration tab can preview the per-step additions, and inventory outputs
include `add_*` columns so each step's planned mineral input is visible.

Run the simulation when the configured IPhreeqc DLL/SO and database are available:

```bash
phreeqpyne run --config scenario.json
```

The `run` command writes `phreeqpyne_input.phr` and `selected_output.csv` into the configured output directory.

## Development checks

```bash
python -m pytest
```
