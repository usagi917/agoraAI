"""Shared age bracket classification utilities.

Two variants:
- age_bracket_4: 4 groups (18-29, 30-49, 50-69, 70+) for selection/evaluation
- age_bracket_5: 5 groups (18-29, 30-39, 40-49, 50-59, 60+) for demographic analysis
"""


def age_bracket_4(age: int) -> str:
    """Classify age into 4 brackets for selection and evaluation."""
    if age < 30:
        return "18-29"
    if age < 50:
        return "30-49"
    if age < 70:
        return "50-69"
    return "70+"


def age_bracket_5(age: int) -> str:
    """Classify age into 5 brackets for demographic analysis."""
    if age < 30:
        return "18-29"
    if age < 40:
        return "30-39"
    if age < 50:
        return "40-49"
    if age < 60:
        return "50-59"
    return "60+"
