def hex_to_kml_color(hex_rgb: str, alpha: int = 180) -> str:
        # KML usa aabbggrr (alpha, blue, green, red)
        if not hex_rgb:
            hex_rgb = "#cccccc"
        s = hex_rgb.lstrip("#")
        if len(s) != 6:
            s = "cccccc"
        r, g, b = s[0:2], s[2:4], s[4:6]
        return f"{alpha:02x}{b}{g}{r}".lower()
    
    
def create_kml(queryset, should_use_color):
    kml_header = '''<?xml version="1.0" encoding="UTF-8"?>
                <kml xmlns="http://www.opengis.net/kml/2.2">
                    <Document>
                        <Style id="style1">
                            <LineStyle>
                                <color>80000000</color>  <!-- Black fill, fully opaque -->
                                <width>2</width>
                            </LineStyle>
                            <PolyStyle>
                                <color>80ffffff</color>  <!-- White line with 80% opacity -->
                                
                            </PolyStyle>
                            <IconStyle>
                                <scale>0</scale>  <!-- Set scale to 0 to hide the icon -->
                            </IconStyle>
                        </Style>
                '''
    kml_footer = '</Document>\n</kml>\n'

    placemarks = ""

    # Loop through each item in the queryset
    for item in queryset:
        # Extract the points for each item
        coordinates = []
        for point in item['map_geo_points']:  # Assuming `map_geo_points` is a JSON field or similar
            lat = point['latitude']
            lng = point['longitude']
            coordinates.append(f"{lng},{lat}")  # KML format is lng,lat
        coordinates.append(f"{item['map_geo_points'][0]['longitude']},{item['map_geo_points'][0]['latitude']}")  # KML format is lng,lat
        
        # Calculate the center of the polygon for the label
        center_lat = sum(float(point['latitude']) for point in item['map_geo_points']) / len(item['map_geo_points'])
        center_lng = sum(float(point['longitude']) for point in item['map_geo_points']) / len(item['map_geo_points'])
        if should_use_color:
            variedade_color = item.get("variedade__cultura__map_color", "#cccccc")
        
            kml_fill = hex_to_kml_color(variedade_color, alpha=180)  # cor de preenchimento
            kml_line = hex_to_kml_color(variedade_color, alpha=255)  # cor da borda
        else:
            kml_fill = hex_to_kml_color("#cccccc", alpha=180)  # cor de preenchimento
            kml_line = hex_to_kml_color("#cccccc", alpha=255)  # cor da borda
        # Create a placemark for each item with additional details
        # Create a placemark for the polygon
        polygon_placemark = f'''
        <Placemark>
            <name>{item['talhao__id_talhao']}</name> <!-- This is the polygon name -->
            <description>Farmbox ID: {item['id_farmbox']}</description>
            <styleUrl>#style1</styleUrl>
            <Style>
                <LineStyle>
                <color>{kml_line}</color>
                <width>2</width>
                </LineStyle>
                <PolyStyle>
                <color>{kml_fill}</color>
                <fill>1</fill>
                <outline>1</outline>
                </PolyStyle>
            </Style>
            <Polygon>
                <outerBoundaryIs>
                    <LinearRing>
                        <coordinates>{" ".join(coordinates)}</coordinates>
                    </LinearRing>
                </outerBoundaryIs>
            </Polygon>
        </Placemark>
        '''

        # Create a separate placemark for the label
        label_placemark = f'''
        <Placemark>
            <name>{item['talhao__id_talhao']}</name> <!-- This is the label -->
            <styleUrl>#style1</styleUrl>  <!-- You can use the same style or define a new one -->
            <Point>
                <coordinates>{center_lng},{center_lat}</coordinates> <!-- Center coordinates for the label -->
            </Point>
            <LabelStyle>
                <color>ff0000ff</color>  <!-- Red label (fully opaque) -->
                <scale>1.2</scale>  <!-- Adjust the label size -->
            </LabelStyle>
        </Placemark>
        '''

        placemarks += polygon_placemark + label_placemark

    return kml_header + placemarks + kml_footer