# CGHE Analyzer

CGHE Analyzer calculates a time-resolved hydrogen diffusion coefficient from carrier-gas hot-extraction measurement signals. Its primary method is an axisymmetric numerical inverse. A full three-dimensional numerical solver and an experimental finite-cylinder analytical inversion are also available.

## Standalone releases and WeldCraft

CGHE Analyzer is also included in the main WeldCraft suite. WeldCraft is the primary development version and may receive fixes and improvements before they are incorporated into a standalone release. Standalone releases are updated periodically when meaningful changes have accumulated.

For the portable Windows release, extract the complete `CGHE Analyzer` folder before opening `CGHE Analyzer.exe`. Running the executable directly from inside an archive can place settings and results in a temporary directory. The standalone application uses the theme last selected in WeldCraft and defaults to the WeldCraft theme for new users.

For the source release, install the pinned dependencies and start the GUI:

```powershell
python -m pip install -r requirements.txt
python "03_CodeBase\p11_gui.py"
```

## Getting started

Open the analyzer from the WeldCraft launcher or the standalone executable, choose a measurement file, review the signal preview, and run the analysis. The Setup sections contain the signal-processing, specimen, mesh, initial-state, solver, and result-saving controls.

For scripted or batch analysis, open `03_CodeBase\p11_run.py`, edit the documented settings near the top, and run the file from the editor. `INPUTS` accepts individual paths and glob patterns. The command-line interface is documented by `03_CodeBase\p11_cli.py --help`.

## Signal processing

Three processing modes are available:

- **Auto** selects a mode from the detected file format. Bruker detector exports use TCD smoothing, replacement-MS exports use Direct processing, and generic or pasted tables use TCD smoothing as the fallback.
- **TCD smoothing** supports quantized detector signals with interpolation, rolling smoothing, a non-increasing post-peak fit, and tail fitting.
- **Direct** applies import correction, linear resampling, and integration to signals that already have adequate resolution.

The preview shows the corrected input, final processed signal, calculated remaining-hydrogen fraction, and the inverse-solver cutoff. The cutoff excludes the late part of a measurement after the remaining-hydrogen fraction falls below the selected threshold, where signal-to-noise commonly becomes poor.

## Initial state and solvers

The initial hydrogen concentration is calculated from the room-temperature diffusivity, preconditioning duration, specimen geometry, mesh, and timestep. A saved preconditioning endpoint can also be loaded when those numerical settings match.

Available solvers are:

- **Axisymmetric Numerical** for the standard rotationally symmetric calculation.
- **Full 3D Numerical** for an explicitly discretized angular domain.
- **Analytical Inversion (Experimental Beta)** for the finite-cylinder analytical model.

## Results and examples

Results are saved as HDF5 files in `02_Results`. Each result includes the settings, processed measurement, time-resolved diffusion curve, evaluation data, and the initial concentration endpoint. Extraction concentration fields are included when their save policy is enabled.

The reported $D_{\mathrm{CGHE}}$ is the median diffusivity in the accepted green evaluation interval. The GUI provides the diffusion result, combined diagnostics, and selectable saved concentration fields. Tabular results can be exported as CSV, and concentration fields can be exported as cell-wise CSV or compressed NumPy data.

Example measurement and result files are provided in `01_Resources\Examples`. Open `CGHE_Example_01_demo.h5` to inspect a complete result with concentration fields.

## Numeric input

Numeric fields use dot-decimal notation independently of the operating-system locale. Decimal and scientific forms such as `0.00005`, `5e-5`, and `5.0e-5` are accepted. Values containing commas are rejected.
