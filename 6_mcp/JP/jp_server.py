from mcp.server.fastmcp import FastMCP
from funciones import obtener_fecha_hoy, sumar
from datetime import date
import math
from typing import List


mcp = FastMCP("jp_server")

@mcp.tool()
async def get_fecha(name: str) -> date:
    """Obtiene la fecha de hoy."""
    return obtener_fecha_hoy()

@mcp.tool()
async def resolver_ecuacion_cuadratica(a: float, b: float, c: float) -> dict:
    """Resuelve ax² + bx + c = 0
    Args:
        a, b, c: Coeficientes de la ecuación
    Returns:
        Dict con raíces y discriminante"""
    discriminante = b**2 - 4*a*c
    if discriminante < 0:
        return {"raices": "complejas", "discriminante": discriminante}
    
    x1 = (-b + math.sqrt(discriminante)) / (2*a)
    x2 = (-b - math.sqrt(discriminante)) / (2*a)
    return {"raices": [x1, x2], "discriminante": discriminante}


@mcp.tool()
async def calcular_matriz_inversa(matriz: List[List[float]]) -> dict:
    """Calcula la inversa de una matriz 3x3
    Args:
        matriz: Lista de listas 3x3
    Returns:
        Matriz inversa o error"""
    import numpy as np
    try:
        m = np.array(matriz)
        inversa = np.linalg.inv(m)
        determinante = np.linalg.det(m)
        return {"inversa": inversa.tolist(), "determinante": determinante}
    except np.linalg.LinAlgError:
        return {"error": "Matriz singular, no tiene inversa"}


@mcp.tool()
async def ajuste_polinomico(puntos: List[dict], grado: int) -> dict:
    """Ajusta un polinomio a puntos (x, y)
    Args:
        puntos: Lista de {"x": float, "y": float}
        grado: Grado del polinomio
    Returns:
        Coeficientes y R²"""
    import numpy as np
    xs = np.array([p["x"] for p in puntos])
    ys = np.array([p["y"] for p in puntos])
    
    coeffs = np.polyfit(xs, ys, grado)
    p = np.poly1d(coeffs)
    y_pred = p(xs)
    ss_res = np.sum((ys - y_pred)**2)
    ss_tot = np.sum((ys - np.mean(ys))**2)
    r_squared = 1 - (ss_res / ss_tot)
    
    return {
        "coeficientes": coeffs.tolist(),
        "r_squared": r_squared,
        "ecuacion": f"y = {' + '.join(f'{c:.4f}x^{grado-i}' for i, c in enumerate(coeffs))}"
    }


@mcp.tool()
async def serie_taylor(funcion: str, x: float, n_terminos: int) -> dict:
    """Aproxima una función con serie de Taylor
    Args:
        funcion: "sin", "cos", "exp", "ln"
        x: Punto a evaluar
        n_terminos: Cantidad de términos
    Returns:
        Aproximación y valor exacto"""
    import math
    
    def sin_taylor(x, n):
        return sum((-1)**k * x**(2*k+1) / math.factorial(2*k+1) for k in range(n))
    
    def cos_taylor(x, n):
        return sum((-1)**k * x**(2*k) / math.factorial(2*k) for k in range(n))
    
    def exp_taylor(x, n):
        return sum(x**k / math.factorial(k) for k in range(n))
    
    funciones = {
        "sin": (sin_taylor, math.sin),
        "cos": (cos_taylor, math.cos),
        "exp": (exp_taylor, math.exp),
    }
    
    if funcion not in funciones:
        return {"error": f"Función no soportada. Usa: {list(funciones.keys())}"}
    
    taylor_fn, exact_fn = funciones[funcion]
    aproximacion = taylor_fn(x, n_terminos)
    exacta = exact_fn(x)
    error = abs(aproximacion - exacta)
    
    return {
        "aproximacion": aproximacion,
        "valor_exacto": exacta,
        "error": error,
        "error_relativo": error / abs(exacta) if exacta != 0 else 0
    }


if __name__ == "__main__":
    mcp.run(transport='stdio')