"""Generate 4 PNG figures for the diploma."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np
from pathlib import Path

OUT = Path("/home/hokma/rtki_project/diplom/figures")
OUT.mkdir(exist_ok=True)

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def figure_1_architecture():
    fig, ax = plt.subplots(figsize=(8.5, 9.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 14)
    ax.axis("off")

    stages = [
        ("Входящий тикет", 12.6, "#E8EEF7"),
        ("Precheck (search_logs)", 11.0, "#D4E1F5"),
        ("RAG (контекстуальные\nрекомендации)", 9.2, "#D4E1F5"),
        ("Planning loop\n(LLM + MCP tools, цикл)", 7.0, "#F5D4D4"),
        ("Верификация\n(get_order_status,\ncheck_eissd_status)", 4.6, "#D4E1F5"),
        ("Build final comment\n(детерминированный шаблон)", 2.4, "#D4E1F5"),
        ("Финализация\n(add_otrs_comment,\nupdate_otrs_ticket)", 0.6, "#D4E1F5"),
    ]
    box_w = 4.2
    box_h = 1.2
    cx = 3.2
    for label, cy, color in stages:
        rect = FancyBboxPatch(
            (cx - box_w / 2, cy - box_h / 2),
            box_w, box_h,
            boxstyle="round,pad=0.06",
            linewidth=1.2, edgecolor="#222", facecolor=color,
        )
        ax.add_patch(rect)
        ax.text(cx, cy, label, ha="center", va="center", fontsize=10.5)

    # arrows between stages
    for i in range(len(stages) - 1):
        y_from = stages[i][1] - box_h / 2
        y_to = stages[i + 1][1] + box_h / 2
        ax.annotate("", xy=(cx, y_to), xytext=(cx, y_from),
                    arrowprops=dict(arrowstyle="->", lw=1.4, color="#222"))

    # MCP sidebar
    mcp_x = 7.6
    mcp_targets = [
        (11.0, "MCP: search_logs"),
        (7.0, "MCP: tools\n(многократно)"),
        (4.6, "MCP: get_order_status\nMCP: check_eissd_status"),
        (0.6, "MCP: add_otrs_comment\nMCP: update_otrs_ticket"),
    ]
    rag_y = 9.2
    rag_rect = FancyBboxPatch(
        (mcp_x - 1.4, rag_y - 0.5), 2.8, 1.0,
        boxstyle="round,pad=0.05",
        linewidth=1.0, edgecolor="#222", facecolor="#FFF6CC",
    )
    ax.add_patch(rag_rect)
    ax.text(mcp_x, rag_y, "RAG Service", ha="center", va="center", fontsize=10)
    ax.annotate("", xy=(mcp_x - 1.4, rag_y), xytext=(cx + box_w / 2, rag_y),
                arrowprops=dict(arrowstyle="->", lw=1.0, color="#555"))

    for cy, lbl in mcp_targets:
        rect = FancyBboxPatch(
            (mcp_x - 1.6, cy - 0.55), 3.2, 1.1,
            boxstyle="round,pad=0.05",
            linewidth=1.0, edgecolor="#222", facecolor="#E2F0DA",
        )
        ax.add_patch(rect)
        ax.text(mcp_x, cy, lbl, ha="center", va="center", fontsize=9.5)
        ax.annotate("", xy=(mcp_x - 1.6, cy), xytext=(cx + box_w / 2, cy),
                    arrowprops=dict(arrowstyle="->", lw=1.0, color="#555"))

    plt.tight_layout()
    plt.savefig(OUT / "fig1_architecture.png", dpi=200, bbox_inches="tight")
    plt.close()


def figure_2_matrix():
    modes = ["A0\nбазовый", "A1\nex-vivo", "A2\nfault inject.", "A3\nкомбинир."]
    levels = ["O0", "O1", "O2"]
    # detection counts (of 9 real bugs, BUG-010 excluded as expected no-detection)
    data = np.array([
        [0, 0, 0],   # A0
        [5, 5, 5],   # A1
        [3, 4, 4],   # A2
        [8, 9, 9],   # A3
    ])

    fig, ax = plt.subplots(figsize=(7.5, 6.0))
    im = ax.imshow(data, cmap="YlGn", vmin=0, vmax=9, aspect="auto")

    ax.set_xticks(range(len(levels)))
    ax.set_xticklabels(levels, fontsize=12)
    ax.set_yticks(range(len(modes)))
    ax.set_yticklabels(modes, fontsize=11)
    ax.set_xlabel("Уровень наблюдаемости", fontsize=12)
    ax.set_ylabel("Режим тестирования", fontsize=12)

    for i in range(len(modes)):
        for j in range(len(levels)):
            v = data[i, j]
            txt_color = "white" if v >= 6 else "#222"
            ax.text(j, i, str(v), ha="center", va="center",
                    color=txt_color, fontsize=14, fontweight="bold")

    cbar = plt.colorbar(im, ax=ax, shrink=0.7)
    cbar.set_label("Обнаружено дефектов (из 9)", fontsize=11)

    ax.set_title("Матрица обнаружения дефектов", fontsize=13, pad=12)
    plt.tight_layout()
    plt.savefig(OUT / "fig2_matrix.png", dpi=200, bbox_inches="tight")
    plt.close()


def figure_3_wrong_diagnostic():
    fig, ax = plt.subplots(figsize=(9.5, 6.5))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 9)
    ax.axis("off")

    def box(x, y, w, h, text, color="#E8EEF7", fontsize=10):
        rect = FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                              boxstyle="round,pad=0.06",
                              linewidth=1.2, edgecolor="#222", facecolor=color)
        ax.add_patch(rect)
        ax.text(x, y, text, ha="center", va="center", fontsize=fontsize)

    def arrow(x1, y1, x2, y2, color="#222", style="->"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle=style, lw=1.3, color=color))

    box(6, 8.2, 7.0, 0.9,
        'LLM вызывает list_otrs_comments(ticket_id="TKT-001")',
        color="#F5D4D4", fontsize=10.5)
    arrow(6, 7.7, 6, 7.0)

    box(6, 6.55, 6.0, 0.9,
        "MCP: вызов выполнен успешно → []",
        color="#D4E1F5")
    arrow(6, 6.1, 6, 5.5)

    box(6, 5.1, 5.6, 0.7,
        'entry.ok = True, entry.tool = "list_otrs_comments"',
        color="#E2F0DA", fontsize=10)
    arrow(6, 4.75, 2.5, 3.5)
    arrow(6, 4.75, 6.0, 3.5)
    arrow(6, 4.75, 9.5, 3.5)
    arrow(6, 4.75, 6.0, 1.4, color="#B22222")

    box(2.5, 3.0, 3.2, 0.9, "O0:\nнет ошибки → не обнаружен",
        color="#FFF6CC", fontsize=9.5)
    box(6.0, 3.0, 3.2, 0.9, "O1:\nнет latency-спайка → не обнаружен",
        color="#FFF6CC", fontsize=9.5)
    box(9.5, 3.0, 3.2, 0.9, "O2:\nатрибуты корректны → не обнаружен",
        color="#FFF6CC", fontsize=9.5)

    box(6.0, 0.7, 6.0, 1.0,
        "SemanticChecker:\nget_order_status НЕ вызван → FAIL",
        color="#F5C6C6", fontsize=11)

    plt.tight_layout()
    plt.savefig(OUT / "fig3_wrong_diagnostic.png", dpi=200, bbox_inches="tight")
    plt.close()


def figure_4_research_to_product():
    fig, ax = plt.subplots(figsize=(9.0, 6.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 9)
    ax.axis("off")

    def box(x, y, w, h, text, color="#E8EEF7", fontsize=10.5):
        rect = FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                              boxstyle="round,pad=0.06",
                              linewidth=1.2, edgecolor="#222", facecolor=color)
        ax.add_patch(rect)
        ax.text(x, y, text, ha="center", va="center", fontsize=fontsize)

    def arrow(x1, y1, x2, y2):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="->", lw=1.3, color="#222"))

    box(2.7, 8.0, 3.6, 0.9, "Эксперимент A0–A3", color="#D4E1F5")
    box(7.3, 8.0, 3.6, 0.9, "LLM-эксперимент", color="#F5D4D4")

    box(2.7, 6.3, 3.6, 0.9, "BUG-007 (LatencyFault 200 мс)", color="#FFF6CC")
    box(7.3, 6.3, 3.6, 0.9, "LLM_WRONG_DIAGNOSTIC", color="#FFF6CC")

    box(2.7, 4.6, 3.6, 0.9, "CHK-I-01..02 (чеклист)", color="#E2F0DA")
    box(7.3, 4.6, 3.6, 0.9, "CHK-L-03..04 (чеклист)", color="#E2F0DA")

    box(2.7, 2.9, 3.6, 0.9, "test_experiment_derived.py", color="#E8EEF7")
    box(7.3, 2.9, 3.6, 0.9, "test_llm_semantic.py", color="#E8EEF7")

    box(5.0, 1.2, 6.5, 1.0,
        "Продуктовый тест-сьют RTK Agent (116 тестов)",
        color="#F5C6C6", fontsize=11)

    for x in (2.7, 7.3):
        arrow(x, 7.55, x, 6.75)
        arrow(x, 5.85, x, 5.05)
        arrow(x, 4.15, x, 3.35)
        arrow(x, 2.45, 5.0, 1.7)

    plt.tight_layout()
    plt.savefig(OUT / "fig4_research_to_product.png", dpi=200, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    figure_1_architecture()
    figure_2_matrix()
    figure_3_wrong_diagnostic()
    figure_4_research_to_product()
    for p in sorted(OUT.glob("*.png")):
        print(f"  {p.name}: {p.stat().st_size // 1024} KB")
