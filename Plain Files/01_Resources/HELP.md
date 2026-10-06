# CGHE Analyzer Help

## Recommended numerical inversion

The axisymmetric numerical solver advances the hydrogen concentration field in a finite cylinder and infers the spatially uniform diffusion coefficient required at each time step to reproduce the measured remaining-hydrogen curve. Hydrogen totals are integrated with cylindrical radial weighting.

The full-3D option performs the same inverse calculation on an actual radial-angular-axial array. The GUI deliberately keeps the initial and boundary conditions angularly uniform.

## Signal processing

Use **Auto** unless the signal origin is known and you want to override it. Native replacement-MS files and replacement-MS files carrying the converter provenance use **Direct** processing because their exported signal is already smoothed and baseline corrected. Bruker TCD files and unknown generic tables use the published **Legacy multistep** TCD recipe. **Custom** exposes the rolling width and pass count, isotonic decay constraint, and exponential-tail options.

The Setup preview plots the complete corrected input and final processed signal together, with the complete calculated remaining-hydrogen fraction below. A grey dashed marker shows where the inverse solver stops at the configurable **Solver cutoff**. The late signal is normally noise-dominated once very little hydrogen remains, so excluding that tail prevents unstable diffusivity estimates; the excluded data remains visible in the preview. File, import, and processing changes refresh the preview automatically after a short delay.

## Initial concentration endpoints

Calculated initial states use the entered room-temperature diffusivity and preconditioning duration. **Build / Save endpoint** stores only the final symmetric radial-axial concentration field and the settings needed to validate it. Loading an endpoint never changes the current settings: every geometry, mesh, or timestep mismatch is listed and the file is rejected.

## Result and saved concentration fields

The **Result** view keeps the selected numerical inversion in front. The experimental analytical comparison is added only when requested, unless analytical inversion was selected as the main method. **Diagnostics** combines diffusivity, remaining fraction, and the processed signal on one time-aligned graph with separate y axes.

If extraction concentration fields were saved during the run, the **Concentration fields** tab lists every saved state. Select any combination to redraw the cutaways. **Export selected data** writes either a tidy CSV containing every selected grid cell or a compressed NPZ containing the original arrays, coordinates, state metadata, and settings.

The shipped `01_Resources/Examples/CGHE_Example_01_demo.h5` result contains 20 saved states and demonstrates all three result views. Until you have produced local results, **Load HDF5** opens the shipped example directory automatically.

## Analytical Inversion — Experimental Beta

When diffusivity is spatially uniform but varies with time, the diffusion equation can be expressed using cumulative diffusion exposure,

`Theta(t) = integral from 0 to t of D(tau) d tau`.

The application evaluates the finite-cylinder remaining-hydrogen function as a function of `Theta`, inverts the measured remaining fraction to recover `Theta(t)`, and differentiates it to estimate the local `D(t)`. A preconditioned state is represented by the prior exposure `D_pre * t_pre` and normalized against the hydrogen remaining after that exposure.

This analytical route is under active development and has not been validated to the same level as the recommended numerical inverse. It is not the classical half-time method.

## Green evaluation interval

The application proposes the locally flattest 0.10-wide remaining-hydrogen interval within `0.10 <= R_H <= 0.55` and after 20 seconds. Drag either green boundary or enter start/end times to review it. `D_CGHE` is the median `D(t)` inside the accepted interval; the complete curve is always retained.

MAE and maximum residual describe how closely the numerical step inversion reproduced the target remaining-hydrogen curve. They are numerical convergence diagnostics, not independent physical validation.
