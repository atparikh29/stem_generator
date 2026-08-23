"""Neuro-Symbolic Solver-Verifier: Physics (Deterministic Templates).

Each AP Physics 1 Mechanics problem maps to a fixed formula template. For the
declared `unknown`, the solver:
  - enforces unit consistency (pint raises on incompatible dimensions),
  - checks parameter realism (sane magnitudes / signs),
  - computes the numeric solution from the givens,
  - verifies the method/answer against the claimed expected answer.

Failures map to FailureCode.UNIT_MISMATCH or FailureCode.MATH_INVALID.
"""
from __future__ import annotations

import math
import re
from typing import Callable

from pint import DimensionalityError

from ..schemas.generator import PhysicsTask
from ..translation.units import Q_, ureg
from .result import CheckResult, FailureCode

G = 9.8 * ureg("m/s**2")  # standard gravity used by the templates


def _q(givens, name):
    """Fetch a given as a pint Quantity; raises KeyError if missing."""
    g = givens[name]
    return g.value * ureg(g.unit) if g.unit else Q_(g.value)


# --- Template solvers: (template, unknown) -> callable(givens) -> Quantity ---

def _kinematics(givens, unknown):
    if unknown == "v":      # v = u + a t
        return _q(givens, "u") + _q(givens, "a") * _q(givens, "t")
    if unknown == "s":      # s = u t + 1/2 a t^2
        t = _q(givens, "t")
        return _q(givens, "u") * t + 0.5 * _q(givens, "a") * t**2
    if unknown == "t":      # t = (v - u) / a
        return (_q(givens, "v") - _q(givens, "u")) / _q(givens, "a")
    if unknown == "a":      # a = (v - u) / t
        return (_q(givens, "v") - _q(givens, "u")) / _q(givens, "t")
    raise KeyError(unknown)


def _newton_friction(givens, unknown):
    if unknown == "a":      # (F_applied - mu m g) / m
        m = _q(givens, "m")
        return (_q(givens, "F_applied") - _q(givens, "mu") * m * G) / m
    if unknown == "friction":   # f = mu m g
        return _q(givens, "mu") * _q(givens, "m") * G
    if unknown == "F_applied":  # F = m a + mu m g
        m = _q(givens, "m")
        return m * _q(givens, "a") + _q(givens, "mu") * m * G
    raise KeyError(unknown)


def _work_energy(givens, unknown):
    if unknown == "work":   # W = F d
        return _q(givens, "F") * _q(givens, "d")
    if unknown == "ke":     # KE = 1/2 m v^2
        return 0.5 * _q(givens, "m") * _q(givens, "v") ** 2
    if unknown == "v":      # from rest: v = sqrt(2 W / m)
        return (2 * _q(givens, "work") / _q(givens, "m")) ** 0.5
    raise KeyError(unknown)


def _impulse_momentum(givens, unknown):
    if unknown == "impulse":    # J = F t
        return _q(givens, "F") * _q(givens, "t")
    if unknown == "momentum":   # p = m v
        return _q(givens, "m") * _q(givens, "v")
    if unknown == "dv":         # dv = J / m
        return _q(givens, "impulse") / _q(givens, "m")
    raise KeyError(unknown)


def _circular_motion(givens, unknown):
    if unknown == "ac":     # a_c = v^2 / r
        return _q(givens, "v") ** 2 / _q(givens, "r")
    if unknown == "force":  # F_c = m v^2 / r
        return _q(givens, "m") * _q(givens, "v") ** 2 / _q(givens, "r")
    if unknown == "v":      # v = sqrt(F r / m)
        return (_q(givens, "force") * _q(givens, "r") / _q(givens, "m")) ** 0.5
    raise KeyError(unknown)


def _angle(givens, name="theta") -> float:
    """A 2D/rotational angle given, in radians (stored dimensionless / 'rad')."""
    return float(givens[name].value)


def _torque(givens, unknown):
    if unknown == "torque":     # tau = r F sin(theta)   (2D)
        return _q(givens, "r") * _q(givens, "F") * math.sin(_angle(givens))
    raise KeyError(unknown)


def _rotational_kinematics(givens, unknown):
    if unknown == "omega":      # omega = omega0 + alpha t
        return _q(givens, "omega0") + _q(givens, "alpha") * _q(givens, "t")
    if unknown == "alpha":      # alpha = (omega - omega0) / t
        return (_q(givens, "omega") - _q(givens, "omega0")) / _q(givens, "t")
    if unknown == "t":          # t = (omega - omega0) / alpha
        return (_q(givens, "omega") - _q(givens, "omega0")) / _q(givens, "alpha")
    raise KeyError(unknown)


def _rotational_dynamics(givens, unknown):
    if unknown == "torque":     # tau = I alpha  (Newton's 2nd law for rotation)
        return _q(givens, "I") * _q(givens, "alpha")
    if unknown == "alpha":      # alpha = tau / I
        return _q(givens, "torque") / _q(givens, "I")
    if unknown == "I":          # I = tau / alpha
        return _q(givens, "torque") / _q(givens, "alpha")
    raise KeyError(unknown)


def _projectile_motion(givens, unknown):
    v0, th = _q(givens, "v0"), _angle(givens)   # 2D projectile, launch angle theta
    if unknown == "range":        # R = v0^2 sin(2 theta) / g
        return v0 ** 2 * math.sin(2 * th) / G
    if unknown == "max_height":   # H = v0^2 sin^2(theta) / (2 g)
        return v0 ** 2 * math.sin(th) ** 2 / (2 * G)
    if unknown == "flight_time":  # T = 2 v0 sin(theta) / g
        return 2 * v0 * math.sin(th) / G
    raise KeyError(unknown)


def _inclined_plane(givens, unknown):
    if unknown == "a":          # a = g (sin theta - mu cos theta)   (2D decomposition)
        th = _angle(givens)
        return G * (math.sin(th) - _q(givens, "mu") * math.cos(th))
    raise KeyError(unknown)


_TEMPLATES: dict[str, Callable] = {
    "kinematics": _kinematics,
    "newton_friction": _newton_friction,
    "work_energy": _work_energy,
    "impulse_momentum": _impulse_momentum,
    "circular_motion": _circular_motion,
    "torque": _torque,
    "rotational_kinematics": _rotational_kinematics,
    "rotational_dynamics": _rotational_dynamics,
    "projectile_motion": _projectile_motion,
    "inclined_plane": _inclined_plane,
}

# Crude realism envelopes (magnitude in SI base) to catch absurd parameters.
_REALISM = {
    "speed": (0, 1000),        # m/s
    "mass": (1e-6, 1e6),       # kg
    "time": (0, 1e5),          # s
    "length": (0, 1e6),        # m
}


def _realism_violation(task: PhysicsTask) -> str | None:
    for name, g in task.givens.items():
        try:
            q = g.value * ureg(g.unit) if g.unit else Q_(g.value)
        except Exception:  # noqa: BLE001
            continue
        if g.unit and ureg(g.unit).dimensionality == ureg("m/s").dimensionality:
            lo, hi = _REALISM["speed"]
            if not (lo <= abs(q.to("m/s").magnitude) <= hi):
                return f"{name}={q} is an unrealistic speed"
        if g.unit and ureg(g.unit).dimensionality == ureg("kg").dimensionality:
            if q.to("kg").magnitude <= 0:
                return f"{name}={q} has non-positive mass"
    return None


# LLMs label givens/unknowns with natural names; map them to each template's
# canonical keys so a correct problem isn't falsely rejected on vocabulary alone.
_ALIASES: dict[str, dict[str, str]] = {
    "kinematics": {
        "velocity": "v", "final_velocity": "v", "speed": "v",
        "initial_velocity": "u", "v0": "u", "u0": "u", "vi": "u", "vf": "v",
        "acceleration": "a", "time": "t", "displacement": "s", "distance": "s",
    },
    "newton_friction": {
        "mass": "m", "force": "F_applied", "applied_force": "F_applied", "f": "F_applied",
        "mu_k": "mu", "friction_coefficient": "mu", "coefficient_of_friction": "mu",
        "acceleration": "a", "friction_force": "friction",
    },
    "work_energy": {
        "force": "F", "distance": "d", "displacement": "d", "mass": "m",
        "velocity": "v", "speed": "v", "kinetic_energy": "ke", "work_done": "work", "w": "work",
    },
    "impulse_momentum": {
        "force": "F", "time": "t", "mass": "m", "velocity": "v", "speed": "v",
        "change_in_velocity": "dv", "delta_v": "dv", "p": "momentum",
    },
    "circular_motion": {
        "mass": "m", "velocity": "v", "speed": "v", "radius": "r",
        "acceleration": "ac", "centripetal_acceleration": "ac", "a": "ac",
        "force": "force", "centripetal_force": "force",
    },
    "torque": {
        "radius": "r", "lever_arm": "r", "distance": "r", "force": "F",
        "angle": "theta", "tau": "torque", "moment": "torque",
    },
    "rotational_kinematics": {
        "initial_angular_velocity": "omega0", "omega_0": "omega0", "w0": "omega0",
        "angular_velocity": "omega", "final_angular_velocity": "omega", "w": "omega",
        "angular_acceleration": "alpha", "a": "alpha", "time": "t",
    },
    "rotational_dynamics": {
        "moment_of_inertia": "I", "inertia": "I", "angular_acceleration": "alpha",
        "a": "alpha", "tau": "torque", "net_torque": "torque", "moment": "torque",
    },
    "projectile_motion": {
        "initial_speed": "v0", "launch_speed": "v0", "speed": "v0", "velocity": "v0",
        "angle": "theta", "launch_angle": "theta", "horizontal_range": "range",
        "r": "range", "height": "max_height", "time_of_flight": "flight_time",
    },
    "inclined_plane": {
        "angle": "theta", "incline_angle": "theta", "mu_k": "mu",
        "friction_coefficient": "mu", "coefficient_of_friction": "mu", "acceleration": "a",
    },
}


# Canonical keys each template's solver understands.
_CANONICAL: dict[str, set[str]] = {
    "kinematics": {"u", "v", "a", "t", "s"},
    "newton_friction": {"m", "F_applied", "mu", "a", "friction"},
    "work_energy": {"F", "d", "work", "m", "v", "ke"},
    "impulse_momentum": {"F", "t", "impulse", "m", "v", "momentum", "dv"},
    "circular_motion": {"m", "v", "r", "ac", "force"},
    "torque": {"r", "F", "theta", "torque"},
    "rotational_kinematics": {"omega0", "omega", "alpha", "t"},
    "rotational_dynamics": {"I", "alpha", "torque"},
    "projectile_motion": {"v0", "theta", "range", "max_height", "flight_time"},
    "inclined_plane": {"theta", "mu", "a"},
}


def _strip(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _canon(template: str, name: str) -> str:
    """Map a natural field name to the template's canonical key.

    Tries, in order: the alias table; a separator-insensitive match against the
    canonical keys (so "a_c"/"A-C" -> "ac"); a separator-insensitive alias match.
    """
    amap = _ALIASES.get(template, {})
    norm = name.strip().lower().replace(" ", "_")
    if norm in amap:
        return amap[norm]
    stripped = _strip(name)
    for key in _CANONICAL.get(template, ()):
        if _strip(key) == stripped:
            return key
    amap_stripped = {_strip(k): v for k, v in amap.items()}
    return amap_stripped.get(stripped, name)


def verify(task: PhysicsTask) -> CheckResult:
    solver = _TEMPLATES.get(task.template)
    if solver is None:
        return CheckResult.fail(FailureCode.MATH_INVALID, f"unknown template {task.template}")

    realism = _realism_violation(task)
    if realism:
        return CheckResult.fail(FailureCode.MATH_INVALID, f"realism: {realism}")

    # Normalize natural field names to the template's canonical keys.
    givens = {_canon(task.template, k): v for k, v in task.givens.items()}
    unknown = _canon(task.template, task.unknown)

    try:
        computed = solver(givens, unknown)
    except KeyError as exc:
        return CheckResult.fail(
            FailureCode.MATH_INVALID,
            f"template {task.template} cannot solve for {task.unknown}; missing {exc}",
        )
    except DimensionalityError as exc:
        return CheckResult.fail(FailureCode.UNIT_MISMATCH, str(exc))
    except Exception as exc:  # noqa: BLE001
        return CheckResult.fail(FailureCode.MATH_INVALID, f"physics solver error: {exc}")

    expected_unit = task.expected_answer.unit or ""
    try:
        target = task.expected_answer.value * ureg(expected_unit) if expected_unit else Q_(task.expected_answer.value)
        computed_in_target = computed.to(target.units) if hasattr(computed, "to") else Q_(computed)
    except DimensionalityError as exc:
        return CheckResult.fail(
            FailureCode.UNIT_MISMATCH,
            f"computed units {getattr(computed, 'units', '?')} != expected {expected_unit}: {exc}",
        )

    cval = float(getattr(computed_in_target, "magnitude", computed_in_target))
    tval = float(getattr(target, "magnitude", target))
    tol = 1e-3 * max(1.0, abs(tval))
    # Display in the target unit, compact form ("125000.0 N", not base units).
    computed_disp = f"{computed_in_target:~}" if hasattr(computed_in_target, "units") else str(computed_in_target)
    target_disp = f"{target:~}" if hasattr(target, "units") else str(target)
    if abs(cval - tval) <= tol:
        return CheckResult.ok("physics answer verified", computed=computed_disp, expected=target_disp)
    return CheckResult.fail(
        FailureCode.MATH_INVALID,
        f"computed {computed_disp} != expected {target_disp}",
        computed=computed_disp,
    )
