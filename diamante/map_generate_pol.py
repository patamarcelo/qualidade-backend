import io
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

import matplotlib
from PIL import Image


matplotlib.use("Agg")

colos_map = {
	'1':    "#e0f7fa",
	'2':	"#b3e5fc",
	'3':	"#81d4fa",
	'4':	"#4fc3f7",
	'5':	"#29b6f6",
	'6':	"#03a9f4",
	'7':	"#039be5",
	'8':	"#0288d1",
	'9':	"#0277bd",
	'10':	"#01579b",
	'11':	"#014f85",
	'12':	"#01386f",
	'13':	"#012259",
	'14':	"#011643",
	'15':	"#000d2c",
	'16':	"#000215"
}

def draw_cartoon_map(
    polygons,
    labels,
    centerid,
    ids_farmbox,
    filled_polygon_index=[],
    filled_color="blue",
    fontsize=10,
    edge_linewidth=0.5,
    planejamento_plantio=False,
    grouped_by_date=[],
    ids_farmbox_planner=[]
):
    fig, ax = plt.subplots(
        edgecolor="none"
    )  # Set edge color of the entire figure to none
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    for i, (polygon, label, centeri, id_farm, planner_id_farmbox) in enumerate(
        zip(polygons, labels, centerid, ids_farmbox, ids_farmbox_planner)
    ):
        if planejamento_plantio == True:
            index_value = next(
                (group['index'] for group in grouped_by_date if planner_id_farmbox in group['list']),
                None
            )
            print(index_value)
            print(planner_id_farmbox)
            filled_color = colos_map.get(str(index_value))
            print('filled new color: ', filled_color)
            ax.add_patch(
                    Polygon(
                        polygon, edgecolor="black", facecolor=filled_color, linewidth=edge_linewidth
                    )
                )
        else:
            if id_farm in filled_polygon_index:
                ax.add_patch(
                    Polygon(
                        polygon, edgecolor="black", facecolor=filled_color, linewidth=edge_linewidth
                    )
                )
            else:
                # filled_color = filled_color if planejamento_plantio == False else 'white'
                ax.add_patch(
                    Polygon(polygon, edgecolor="black", facecolor='white', linewidth=edge_linewidth)
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
