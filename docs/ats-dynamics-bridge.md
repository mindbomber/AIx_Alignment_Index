# ATS Dynamics Bridge

The Expanded Edition maps AIx measurements to directional proxies for the ATS equation:

```text
alignment change = -pressure * error * (1 - feedback)
                   - irreversible loss + correction - hidden drift
```

AIx Open exposes:

- pressure: positive constraint skew divided by 100
- error: `(100 - P) / 100`
- feedback fidelity: `F / 100`
- irreversible loss: `LVP / 24`
- correction capacity: `F3 / 5`
- hidden drift: declared `hidden_drift`, defaulting to zero when unavailable

The result is included in every score report under `dynamics_proxy`.

This is a directional diagnostic, not a measured rate, causal estimate, or physical law.
Comparisons require a consistent instrument, time horizon, and hidden-drift definition.

