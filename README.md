# PhreeqPyne

Building a handful simulation paradigm for hydrothermal water-rock simulation using PhreeqPy with multi-programming language.

## Project-level direction

`CFAS_therm_240C_Ccp_SCM_multistage.ipynb` remains the exploratory notebook, while reusable logic is being migrated into the `phreeqpyne` Python package. The package currently provides:

- typed, serializable model/runtime configuration;
- staged boundary-fluid interpolation;
- PHREEQC input-script generation through an extensible simulation workflow registry;
- the current `transport` workflow plus a path for future ADVECTION, equilibrium-batch, inverse-modeling, or coupled workflows;
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

Run the simulation when the configured IPhreeqc DLL/SO and database are available:

```bash
phreeqpyne run --config scenario.json
```

The `run` command writes `phreeqpyne_input.phr` and `selected_output.csv` into the configured output directory.

## Development checks

```bash
python -m pytest
```
