import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

import pygame
import math
import json
import os

from .path_finder import build_graph, load_streets, Graph, Node
from .player_grabber import PlayerCoords

cos30 = math.cos(math.radians(30))
sin30 = math.sin(math.radians(30))

CELL_SIZE = 300

pygame.init()

class RenderEngine:
    def __init__(self, street_data_path: str, world_data_path: str, cache_name: str|None = None):
        self.__street_path = street_data_path
        self.__worldmap_path = world_data_path

        street_tree = ET.parse(self.__street_path)
        world_tree  = ET.parse(self.__worldmap_path)

        self.__display = pygame.display.set_mode((800, 600))
        pygame.display.set_caption("Project Zomboid - Route Finder [LOADING]")

        self.__coord_grabber = PlayerCoords()

        self.__root_streets = street_tree.getroot()
        self.__root_world = world_tree.getroot()

        self.__streets_iso, self.__bounds_iso = self.__load_streets(convert_isometric=True, get_street_names=True)
        self.__world_iso, self.__bounds_world_iso = self.__load_worldmap(convert_isometric=True)

        self.__path_colour = (0, 0, 255)
        self.__active_path = []
        self.__active_streets = []

        self.__background_colour = (242, 239, 233)

        self.__road_small_colour = (181, 181, 181)
        self.__road_medium_color = (137, 137, 137)
        self.__road_large_colour = (73, 73, 73)

        self.__feature_colours = {
            "water": (61, 195, 229),
            "building": (209, 209, 209),
            "railway": (30, 30, 30)
        }

        self.__feature_colour_trail = (153, 95, 21)

        self.__road_small_threshold = 5
        self.__road_large_threshold = 10
        
        self.__viewport = self.__bounds_iso
        self.__zooms = [x/10 for x in range(8, 12, 1)]
        self.__zoom = 1
        self.running = False
        self.__render_view = None

        self.__player_location = self.__coord_grabber.get_coords()

        self.__zoom_at(0.5, (self.__display.get_width() // 4, self.__display.get_height() // 2))
        self.__load_slate = self.__create_rendering(self.__viewport, self.__display.get_size())

        self.__graph: Graph = self.__get_graph(cache_name)
        self.__last_xyz = self.__coord_grabber.get_coords()
        self.__last_target = [0 ,0]


    def __get_graph(self, cache_name: str | None) -> Graph:
        cache_dir = os.path.join("data", "cache")
        os.makedirs(cache_dir, exist_ok=True)

        cache_path = os.path.join(cache_dir, f"{cache_name}.cache")
        has_cache = os.path.exists(cache_path) and cache_name is not None

        if has_cache:
            print("[CACHE] Loading graph from:", cache_path)

            with open(cache_path, "r") as f_json:
                data = json.load(f_json)

            return Graph.from_dict(data)

        else:
            print("[CACHE] No graph cache detected")
            graph = build_graph(
                load_streets(
                    self.__street_path,
                    convert_func=self.__convert_world_to_isometric
                ),
                tolerance=10,
                render_callback=self.__graph_load_render_callback
            )

            if cache_name is not None:
                print("[CACHE] Saving graph to:", cache_path)
                with open(cache_path, "w") as f_json:
                    json.dump(graph.to_dict(), f_json)

            return graph

    def __graph_load_render_callback(self, points, colour):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                print("Exited while loading")
                exit(0)

        source_width = self.__viewport[1][0] - self.__viewport[0][0] + 1
        source_height = self.__viewport[1][1] - self.__viewport[0][1] + 1

        scale_x = self.__display.get_width() / source_width
        scale_y = self.__display.get_height() / source_height

        offset_x, offset_y = self.__viewport[0]
        scale = max(scale_x, scale_y)

        pts = [
            ((x - offset_x) * scale, (y - offset_y) * scale)
            for x, y in points
        ]

        pygame.draw.lines(
            self.__load_slate,
            colour,
            False,
            pts,
            width=2
        )

        self.__display.blit(self.__load_slate, (0, 0))
        pygame.display.flip()



    def get_player_position(self):
        """ Returns the ISO world position """
        px, py, pz = self.__coord_grabber.get_coords()
        return self.__convert_world_to_isometric(px, py)

    def get_player_position_node(self):
        return self.__graph.get_closest_node(*self.get_player_position())

    def create_path_to_world_xy(self, iso_x, iso_y):
        self.__last_target = [iso_x, iso_y]

        rect = pygame.sysfont.SysFont("monospace", 26).render("Generating Route...", True, (255, 0, 0))
        self.__display.blit(rect, ((self.__display.get_width() - rect.get_width()) // 2, 20))
        pygame.display.flip()

        closest_node = self.__graph.get_closest_node(iso_x, iso_y)
        self.__active_path = self.__graph.find_path(self.get_player_position_node(), closest_node)

        self.__active_streets = [
            (edge.street, node.point, self.__active_path[i+1].point)
            for i, node in enumerate(self.__active_path[:-1])
            if (edge := node.get_connected_edge(self.__active_path[i+1])) is not None
        ]

        self.update_render_view()


    def create_image_from_road_network(self, output_path: str, isometric: bool) -> None:
        streets, bounds = self.__load_streets(convert_isometric=isometric)
        (min_x, min_y), (max_x, max_y) = bounds
        padding = 20

        img_width = int(max_x - min_x + 2 * padding)
        img_height = int(max_y - min_y + 2 * padding)

        # Create black image
        img = Image.new("L", (img_width, img_height), 0)
        draw = ImageDraw.Draw(img)

        # Draw streets in white
        for pts, width, name in streets:
            shifted = [
                (x - min_x + padding, y - min_y + padding)
                for x, y in pts
            ]
            if len(shifted) >= 2:
                draw.line(shifted, fill=255, width=width)

        img.save(output_path)

    def __load_streets(self, convert_isometric=False, get_street_names=False):
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")

        streets = []

        for street in self.__root_streets.findall("street"):
            width = int(street.get("width", 1))
            name = street.get("name", f"Unknown Street {len(street)}")

            pts = []
            for p in street.find("points").findall("point"): # NOQA
                x = float(p.get("x")) # NOQA
                y = float(p.get("y")) # NOQA

                if convert_isometric:
                    x, y = self.__convert_world_to_isometric(x, y)

                pts.append((x, y))

                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

            if get_street_names:
                streets.append((pts, width, name))
            else:
                streets.append((pts, width))

        bounds = ((math.floor(min_x), math.floor(min_y)), (math.ceil(max_x), math.ceil(max_y)))

        return streets, bounds

    def __load_worldmap(self, convert_isometric=False):
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")

        features = []

        for cell in self.__root_world.findall("cell"):
            cell_x = int(cell.get("x")) # NOQA
            cell_y = int(cell.get("y")) # NOQA

            world_offset_x = cell_x * CELL_SIZE
            world_offset_y = cell_y * CELL_SIZE

            for feature in cell.findall("feature"):
                geometry = feature.find("geometry")

                # Polygon points in world coordinates
                polygon = []
                for point in geometry.find("coordinates").findall("point"):
                    x = world_offset_x + float(point.get("x")) # NOQA
                    y = world_offset_y + float(point.get("y")) # NOQA

                    if convert_isometric:
                        x, y = self.__convert_world_to_isometric(x, y)

                    polygon.append((x, y))

                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)

                # Properties
                properties = {}
                for prop in feature.find("properties").findall("property"):
                    properties[prop.get("name")] = prop.get("value")

                features.append({
                    "geometry_type": geometry.get("type"),
                    "polygon": polygon,
                    "properties": properties,
                })


        if len(features) == 0:
            raise ValueError("No data loaded")

        bounds = ((math.floor(min_x), math.floor(min_y)), (math.ceil(max_x), math.ceil(max_y)))

        return features, bounds

    @staticmethod
    def __convert_world_to_isometric(x, y):
        X = (x - y) * cos30
        Y = (x + y) * sin30
        return X, Y

    @staticmethod
    def __convert_isometric_to_world(X,Y):
        x = (X / cos30 + Y / sin30) / 2
        y = (Y / sin30 - X / cos30) / 2
        return x, y

    def __convert_screen_to_world_iso(self, x, y):
        source_width = self.__viewport[1][0] - self.__viewport[0][0] + 1
        source_height = self.__viewport[1][1] - self.__viewport[0][1] + 1

        scale_x = self.__display.get_width() / source_width
        scale_y = self.__display.get_height() / source_height

        offset_x, offset_y = self.__viewport[0]
        scale = max(scale_x, scale_y)

        iso_x = (x / scale) + offset_x
        iso_y = (y / scale) + offset_y

        return iso_x, iso_y

    def __road_width_to_colour(self, width: int) -> tuple[int, int, int]:
        if width <= self.__road_small_threshold:
            return self.__road_small_colour

        elif width > self.__road_large_threshold:
            return self.__road_large_colour

        return self.__road_medium_color

    def __create_rendering(self, source_view_box: tuple[tuple[int, int], tuple[int, int]],
                                output_view_shape:  tuple[int, int]) -> pygame.Surface:
        """ Creates a Surface of the output_view_box size, and containing a view of everything within the source_view_box """
        surface = pygame.Surface(output_view_shape)
        surface.fill(self.__background_colour)

        source_width = source_view_box[1][0] - source_view_box[0][0] + 1
        source_height = source_view_box[1][1] - source_view_box[0][1] + 1

        scale_x = output_view_shape[0] / source_width
        scale_y = output_view_shape[1] / source_height

        scale = max(scale_x, scale_y)

        offset_x, offset_y = source_view_box[0]

        for points, width, name in self.__streets_iso:
            colour = self.__road_width_to_colour(width)

            pts = [
                ((x-offset_x) * scale, (y-offset_y) * scale)
                for x, y in points
            ]

            pygame.draw.lines(
                surface,
                colour,
                closed=False,
                points=pts,
                width=math.ceil(width * scale)
            )

        for feature in self.__world_iso:
            if feature["geometry_type"] == "Polygon":
                pts = [
                    ((x-offset_x) * scale, (y-offset_y) * scale)
                    for x, y in feature["polygon"]
                ]

                props = list(feature["properties"].keys())

                feature_type = None
                feature_data = None
                if props:
                    feature_type: str = props[0]
                    feature_data = feature["properties"][feature_type]

                colour = None
                if feature_type == "highway" and feature_data == "trail":
                    colour = self.__feature_colour_trail

                if feature_type in self.__feature_colours or colour:
                    if colour is None:
                        colour = self.__feature_colours[feature_type] # NOQA

                    pygame.draw.polygon(
                        surface,
                        colour,
                        pts
                    )


        if self.__active_path:
            for name, start, end in self.__active_streets:
                start = ((start[0] - offset_x) * scale, (start[1] - offset_y) * scale)
                end = ((end[0] - offset_x) * scale, (end[1] - offset_y) * scale)

                pygame.draw.line(
                    surface,
                    self.__path_colour,
                    start, end,
                    width=5
                )


        return surface


    def __set_viewport(self, min_x, min_y, max_x, max_y):
        self.__viewport = (
            (min_x, min_y),
            (max_x, max_y)
        )

    def __pan(self, dx_pixels, dy_pixels):
        (min_x, min_y), (max_x, max_y) = self.__viewport

        view_w = max_x - min_x
        view_h = max_y - min_y

        screen_w, screen_h = self.__display.get_size()

        world_dx = dx_pixels * (view_w / screen_w)
        world_dy = dy_pixels * (view_h / screen_h)

        self.__set_viewport(
            min_x - world_dx,
            min_y - world_dy,
            max_x - world_dx,
            max_y - world_dy,
        )

        self.update_render_view()

    def __zoom_at(self, factor, mouse_pos):
        screen_w, screen_h = self.__display.get_size()
        mx, my = mouse_pos

        mx -= screen_w // 4  # Bodge
        my -= screen_h // 8  # Bodge

        (min_x, min_y), (max_x, max_y) = self.__viewport

        view_w = max_x - min_x
        view_h = max_y - min_y


        # Mouse position in world space
        world_x = min_x + (mx / screen_w) * view_w
        world_y = min_y + (my / screen_h) * view_h

        new_w = view_w / factor
        new_h = view_h / factor

        rx = mx / screen_w
        ry = my / screen_h

        new_min_x = world_x - rx * new_w
        new_min_y = world_y - ry * new_h

        self.__set_viewport(
            new_min_x,
            new_min_y,
            new_min_x + new_w,
            new_min_y + new_h,
        )

        self.update_render_view()

    def update_render_view(self):
        self.__render_view = self.__create_rendering(self.__viewport, self.__display.get_size())
        self.__render_player()

    def __distance_moved(self):
        x1, y1, z1 = self.__coord_grabber.get_coords()
        self.__player_location = [x1, y1, z1]

        x2, y2, z2 = self.__last_xyz

        return math.sqrt(
            (x2 - x1) ** 2 +
            (y2 - y1) ** 2 +
            (z2 - z1) ** 2
        )


    def __render_player(self):
        source_width = self.__viewport[1][0] - self.__viewport[0][0] + 1
        source_height = self.__viewport[1][1] - self.__viewport[0][1] + 1

        scale_x = self.__display.get_width() / source_width
        scale_y = self.__display.get_height() / source_height

        scale = max(scale_x, scale_y)

        offset_x, offset_y = self.__viewport[0]

        px, py, pz = self.__player_location

        x, y = self.__convert_world_to_isometric(px, py)

        pygame.draw.circle(
            self.__render_view,
            (255, 0, 0),
            ((x - offset_x) * scale, (y - offset_y) * scale),
            radius=3 * (1 / self.__zoom)
        )

    def run(self):
        pygame.display.set_caption("Project Zomboid - Route Finder")

        self.running = True

        self.update_render_view()

        left_mouse_down = False

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        left_mouse_down = True

                    elif event.button == 3:
                        iso_x, iso_y = self.__convert_screen_to_world_iso(*event.pos)
                        self.create_path_to_world_xy(iso_x, iso_y)

                if event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        left_mouse_down = False

                if event.type == pygame.MOUSEMOTION:
                    if left_mouse_down:
                        dx, dy = event.rel
                        self.__pan(dx, dy)

                if event.type == pygame.MOUSEWHEEL:
                    if event.y > 0:
                        self.__zoom_at(1.15, pygame.mouse.get_pos())
                    elif event.y < 0:
                        self.__zoom_at(1 / 1.15, pygame.mouse.get_pos())

            if self.__active_path:
                if len(self.__active_streets) == 0:
                    self.__active_path = []
                    self.__active_streets = []

            if self.__distance_moved() > 10:
                self.__last_xyz = self.__coord_grabber.get_coords()

                if self.__active_path:
                    self.create_path_to_world_xy(*self.__last_target)

                    last_x, last_y = self.__convert_world_to_isometric(self.__last_xyz[0], self.__last_xyz[1])

                    view_w = self.__viewport[1][0] - self.__viewport[0][0]
                    view_h = self.__viewport[1][1] - self.__viewport[0][1]

                    offset_x = view_w * 1/4

                    self.__set_viewport(
                        (last_x + offset_x) - view_w / 2,
                        last_y - view_h / 2,
                        (last_x + offset_x) + view_w / 2,
                        last_y + view_h / 2,
                    )

                self.update_render_view()


            self.__display.blit(self.__render_view, (0, 0))

            pygame.display.flip()