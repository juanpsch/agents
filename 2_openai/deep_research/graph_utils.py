import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
from agents import Agent


def _node_id(agent: Agent) -> str:
    return agent.name


def _tool_names(agent: Agent) -> list[str]:
    names = []
    for t in agent.tools or []:
        if hasattr(t, "name"):
            names.append(t.name)
        else:
            names.append(type(t).__name__)
    return names


def _model_str(agent: Agent) -> str:
    return agent.model if isinstance(agent.model, str) else type(agent.model).__name__


def show_graph(steps: list[dict], figsize=(10, 7)) -> None:
    """
    Renderiza el pipeline de agentes como grafo inline en el notebook.

    Cada paso es un dict con:
      - agent    : Agent object (requerido)
      - to       : list[Agent] agentes destino (default [])
      - label    : str etiqueta del edge (default "")
      - parallel : bool indica ejecución paralela (default False)
    """
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_facecolor("#1e1e1e")
    fig.patch.set_facecolor("#1e1e1e")
    ax.axis("off")

    n = len(steps)
    # Posiciones verticales, centradas
    positions = {step["agent"].name: (0.5, 1 - (i / (n - 1 if n > 1 else 1)) * 0.85 - 0.05)
                 for i, step in enumerate(steps)}

    box_w, box_h = 0.52, 0.10

    # Dibuja edges primero (por debajo de los nodos)
    for step in steps:
        src_name = step["agent"].name
        sx, sy = positions[src_name]
        for target in step.get("to", []):
            tgt_name = target.name
            tx, ty = positions[tgt_name]
            ax.annotate(
                "",
                xy=(tx, ty + box_h / 2),
                xytext=(sx, sy - box_h / 2),
                arrowprops=dict(arrowstyle="-|>", color="#4a9eff", lw=1.5),
                xycoords="axes fraction",
                textcoords="axes fraction",
            )
            label = step.get("label", "")
            if label:
                mx = (sx + tx) / 2 + 0.04
                my = (sy + ty) / 2
                ax.text(mx, my, label, transform=ax.transAxes,
                        color="#aaaaaa", fontsize=8, ha="left", va="center")

    # Dibuja nodos
    for step in steps:
        agent = step["agent"]
        name = agent.name
        x, y = positions[name]
        tools = _tool_names(agent)
        model = _model_str(agent)
        parallel = step.get("parallel", False)

        tool_str = "🔧 " + ", ".join(tools) if tools else "sin tools"
        parallel_str = "  ⚡ paralelo" if parallel else ""
        node_label = f"{name}\n{model} · {tool_str}{parallel_str}"

        fancy = mpatches.FancyBboxPatch(
            (x - box_w / 2, y - box_h / 2), box_w, box_h,
            boxstyle="round,pad=0.02",
            linewidth=1.5,
            edgecolor="#4a9eff",
            facecolor="#1a3a5c",
            transform=ax.transAxes,
            clip_on=False,
        )
        ax.add_patch(fancy)
        ax.text(x, y, node_label, transform=ax.transAxes,
                color="white", fontsize=9, ha="center", va="center",
                fontfamily="monospace")

    plt.tight_layout()
    plt.show()
