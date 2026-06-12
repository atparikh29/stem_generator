from app.agents import grader


def test_grade_math_equivalent_forms():
    task = {"domain": "math", "kind": "derivative", "variable": "x",
            "expression": "x**2", "expected_answer": "2*x"}
    assert grader.grade(task, "2*x")[0]
    assert grader.grade(task, "x + x")[0]      # equivalent form
    assert not grader.grade(task, "x")[0]


def test_grade_physics_numeric_tolerance():
    task = {"domain": "physics", "template": "kinematics",
            "givens": {"u": {"value": 5, "unit": "m/s"}},
            "unknown": "v", "expected_answer": {"value": 11.0, "unit": "m/s"}}
    assert grader.grade(task, "11")[0]
    assert grader.grade(task, "11.005")[0]
    assert not grader.grade(task, "12")[0]
