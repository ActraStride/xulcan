def calculator(a: int, b: int, op: str = "+") -> dict:
    """A simple deterministic tool for performing basic math operations.
    
    Returns a dictionary so it serializes cleanly to JSON.
    """
    if op == "+": return {"result": a + b}
    if op == "-": return {"result": a - b}
    if op == "*": return {"result": a * b}
    return {"error": f"unknown operator: {op}"}