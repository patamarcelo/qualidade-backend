import io
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

import matplotlib
from PIL import Image


matplotlib.use("Agg")

import datetime

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

colors_map = {
    '1': "#81c784",   # verde médio
    '2': "#4caf50",   # verde
    '3': "#388e3c",   # verde escuro
    '4': "#1b5e20",   # verde mais escurow

    '5': "#fdd835",   # amarelo vivo
    '6': "#fbc02d",   # amarelo escuro
    '7': "#f9a825",   # dourado queimado
    '8': "#f57f17",   # amarelo-âmbar escuro

    '9': "#fb8c00",   # laranja médio
    '10': "#f57c00",  # laranja mais escuro
    '11': "#ef6c00",  # quase ferrugem
    '12': "#e65100",  # laranja queimado escuro

    '13': "#e57373",  # vermelho médio
    '14': "#ef5350",  # vermelho forte
    '15': "#e53935",  # vermelho mais forte
    '16': "#b71c1c"   # vermelho escuro
}


colors_map = {
    '1':  "#fffde7",  # amarelo bem claro
    '2':  "#fff9c4",
    '3':  "#fff59d",
    '4':  "#fff176",
    '5':  "#ffee58",
    '6':  "#ffeb3b",  # amarelo padrão
    '7':  "#fdd835",
    '8':  "#fbc02d",
    '9':  "#f9a825",
    '10': "#f57f17",
    '11': "#d9a400",
    '12': "#bf9100",
    '13': "#a57e00",
    '14': "#8c6b00",
    '15': "#735800",
    '16': "#594500",  # amarelo queimado / dourado escuro
}


def draw_cartoon_map(
    polygons,
    labels,
    centerid,
    ids_farmbox,
    filled_polygon_index=[],
    filled_color="white",
    fontsize=14,
    edge_linewidth=0.5,
    planejamento_plantio=False,
    grouped_by_date=[],
    ids_farmbox_planner=[],
    color_array=[],
    planned_date=[],
    print_for_planned_date=True,
    selected_color=""
):
    fig, ax = plt.subplots(
        edgecolor="none"
    )  # Set edge color of the entire figure to none
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    for i, (polygon, label, centeri, id_farm, planner_id_farmbox, planned_date_color) in enumerate(
        zip(polygons, labels, centerid, ids_farmbox, ids_farmbox_planner, planned_date)
    ):
        if planejamento_plantio == True:
            index_value = next(
                (group['index'] for group in grouped_by_date if planner_id_farmbox in group['list']),
                None
            )
            print(index_value)
            print(planner_id_farmbox)
            filled_color = colors_map.get(str(index_value), "white")
            if selected_color and selected_color != '#FFF':
                filled_color = selected_color
            print('filled new color: ', filled_color)
            ax.add_patch(
                    Polygon(
                        polygon, edgecolor="black", facecolor=filled_color, linewidth=edge_linewidth
                    )
                )
        if print_for_planned_date:
            ax.add_patch(
                    Polygon(polygon, edgecolor="black", facecolor=planned_date_color, linewidth=edge_linewidth)
                )
        else:
            if id_farm in filled_polygon_index:
                
                new_filled_color = filled_color
                if selected_color and selected_color != '#FFF':
                    new_filled_color = selected_color
                if color_array:
                    get_color = [item["color_selected"] 
                                for item in color_array 
                                if item["id_farmbox"] == planner_id_farmbox]
                    if get_color:
                        new_filled_color = get_color[0]
                    else:
                        new_filled_color = filled_color
                
                ax.add_patch(
                    Polygon(
                        polygon, edgecolor="black", facecolor=new_filled_color, linewidth=edge_linewidth
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
            fontweight='bold',  # deixa em negrito
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
