import io
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

import matplotlib
from PIL import Image


matplotlib.use("Agg")


def draw_cartoon_map(
    polygons,
    labels,
    centerid,
    ids_farmbox,
    filled_polygon_index=[],
    filled_color="blue",
    fontsize=10,
    edge_linewidth=0.5
):
    fig, ax = plt.subplots(
        edgecolor="none"
    )  # Set edge color of the entire figure to none
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    for i, (polygon, label, centeri, id_farm) in enumerate(
        zip(polygons, labels, centerid, ids_farmbox)
    ):
        if id_farm in filled_polygon_index:
            ax.add_patch(
                Polygon(
                    polygon, edgecolor="black", facecolor=filled_color, linewidth=edge_linewidth
                )
            )
        else:
            ax.add_patch(
                Polygon(polygon, edgecolor="black", facecolor="white", linewidth=edge_linewidth)
            )
        # ax.add_patch(Polygon(polygon, edgecolor="black", facecolor="none"))
        centroid = centeri
        ax.text(
            centroid[0],
            centroid[1],
            label,
            ha="center",
            va="center",
            fontsize=fontsize,
            rotation=270,
        )
    ax.autoscale()
    ax.set_aspect("equal", "box")
    ax.set_facecolor("whitesmoke")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(False)

    # Create a buffer to store the image data
    buffer = io.BytesIO()
    plt.savefig(
        buffer,
        format="png",
        dpi=300,
        bbox_inches="tight",
        pad_inches=0,
        transparent=True,
    )  # Save the figure to the buffer
    plt.close(fig)
    buffer.seek(0)
    image = Image.open(buffer)

    # Rotate the image by 270 degrees
    rotated_image = image.rotate(90, expand=True)
    
    rotated_buffer = io.BytesIO()

    # Save the rotated image to the new buffer
    rotated_image.save(rotated_buffer, format="png")

    # Move the buffer position to the beginning
    rotated_buffer.seek(0)


    return rotated_buffer
