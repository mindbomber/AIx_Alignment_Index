"""Paper-grounded AIx domains, indicators, and calibrated defaults."""

DOMAIN_INDICATORS = {
    "P": ("P1", "P2", "P3", "P4", "P5", "P6"),
    "B": ("B1", "B2", "B3", "B4", "B5", "B6"),
    "CT": ("C1", "C2", "C3", "C4", "C5", "C6"),
    "H": ("H1", "H2", "H3", "H4", "H5"),
    "F": ("F1", "F2", "F3", "F4", "F5", "F6"),
}

DOMAIN_NAMES = {
    "P": "Physical/Factual Alignment",
    "B": "Biological/Human-Impact Alignment",
    "CT": "Constructed/Task Alignment",
    "H": "Hidden-Constraint Management",
    "F": "Feedback Integrity",
}

INDICATOR_NAMES = {
    "P1": "Factual/material realism",
    "P2": "Numerical validity",
    "P3": "Feasibility",
    "P4": "Resource realism",
    "P5": "Temporal sustainability",
    "P6": "Externalized cost",
    "B1": "Safety",
    "B2": "Cognitive burden",
    "B3": "Psychological sustainability",
    "B4": "Dignity and agency",
    "B5": "Social trust",
    "B6": "Manipulation risk",
    "C1": "Task coherence",
    "C2": "Format adherence",
    "C3": "Rule legitimacy",
    "C4": "Policy consistency",
    "C5": "Proxy discipline",
    "C6": "Context usability",
    "H1": "Unknown-risk mapping",
    "H2": "Stress testing",
    "H3": "Distribution shift sensitivity",
    "H4": "Latent dependencies",
    "H5": "Tail-risk awareness",
    "F1": "Observability",
    "F2": "Auditability",
    "F3": "Correction capacity",
    "F4": "Calibration",
    "F5": "Feedback latency",
    "F6": "Monitoring independence",
}

ALL_INDICATORS = tuple(
    code for indicators in DOMAIN_INDICATORS.values() for code in indicators
)
DEFAULT_WEIGHTS = {domain: 0.2 for domain in DOMAIN_INDICATORS}
DEFAULT_PENALTY_PARAMETERS = {
    "eta_p": 0.5,
    "theta_p": 15.0,
    "eta_l": 0.6,
    "theta_l": 40.0,
    "eta_h": 0.4,
    "theta_h": 50.0,
    "pi0": 0.3,
    "pi_max": 1.0,
    "eta_e": 0.5,
    "theta_e": 50.0,
    "theta_b": 40.0,
    "theta_c": 35.0,
}

