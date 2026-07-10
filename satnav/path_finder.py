import math
import xml.etree.ElementTree as ET  # NOQA
import heapq
import itertools

def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def close(a, b, eps=1.0):
    return distance(a, b) <= eps


def segment_intersection(a, b, c, d):
    """
    Returns intersection point of segments AB and CD.
    Returns None if they don't intersect.
    """

    x1, y1 = a
    x2, y2 = b
    x3, y3 = c
    x4, y4 = d

    denominator = (
        (x1 - x2) * (y3 - y4)
        - (y1 - y2) * (x3 - x4)
    )

    if denominator == 0:
        return None

    px = (
        (x1*y2 - y1*x2) * (x3-x4)
        - (x1-x2) * (x3*y4 - y3*x4)
    ) / denominator

    py = (
        (x1*y2 - y1*x2) * (y3-y4)
        - (y1-y2) * (x3*y4 - y3*x4)
    ) / denominator


    def within(v, na: int | float, nb: int | float):
        return min(na, nb) - 1e-9 <= v <= max(na, nb) + 1e-9


    if (
        within(px, x1, x2)
        and within(py, y1, y2)
        and within(px, x3, x4)
        and within(py, y3, y4)
    ):
        return px, py

    return None


# Graph:

class Node:
    def __init__(self, x, y, node_id):
        self.x = x
        self.y = y
        self.edges = []
        self.id = node_id

    @property
    def point(self):
        return self.x, self.y

    def __str__(self):
        return f"Node({self.x}, {self.y}, edge_count={len(self.edges)})"

    def get_connected_edge(self, target_node):
        for edge in self.edges:
            if self == edge.a and target_node == edge.b:
                return edge

            if self == edge.b and target_node == edge.a:
                return edge
        
        return None

    def to_dict(self):
        return {
            "x": self.x,
            "y": self.y,
            "id": self.id,
            "edges": [
                edge.id for edge in self.edges
            ]
        }

    @staticmethod
    def from_dict(data):
        node = Node(data["x"], data["y"], data["id"])
        return node, data["edges"]


class Edge:
    def __init__(self, a, b, street, width, edge_id):
        self.a = a
        self.b = b
        self.street = street
        self.width = width
        self.length = distance(a.point, b.point) * (1 - (0.5 * width/15))
        self.id = edge_id

    def to_dict(self):
        return {
            "nodes": {
                "a": self.a.id,
                "b": self.b.id
            },
            "street": self.street,
            "width": self.width,
            "id": self.id
        }

    @staticmethod
    def from_dict(data, nodes: list[Node]):
        return Edge(
            nodes[int(data["nodes"]["a"])],
            nodes[int(data["nodes"]["b"])],
            data["street"],
            int(data["width"]),
            int(data["id"])
        )

class Graph:
    def __init__(self):
        self.nodes = []
        self.edges = []

    def get_node(self, point, tolerance=1.0):
        for node in self.nodes:
            if close(node.point, point, tolerance):
                return node

        node = Node(*point, len(self.nodes))
        self.nodes.append(node)
        return node


    def add_edge(self, a, b, street, width):
        edge = Edge(a, b, street, width, len(self.edges))

        a.edges.append(edge)
        b.edges.append(edge)
        self.edges.append(edge)

    def get_closest_node(self, x, y, get_distance=False):
        min_distance = math.inf
        best_node = None

        for node in self.nodes:
            dist = distance((x, y), node.point)

            if dist < min_distance:
                min_distance = dist
                best_node = node

        if get_distance:
            return min_distance
        return best_node

    def find_path(self, start, goal):
        counter = itertools.count()

        distance_map = {start: 0}
        previous = {}

        queue = [
            (0, next(counter), start)
        ]

        visited = set()

        while queue:
            current_distance, _, current = heapq.heappop(queue)

            if current in visited:
                continue

            visited.add(current)

            if current == goal:
                break

            for edge in current.edges:
                neighbour = (
                    edge.b
                    if edge.a == current
                    else edge.a
                )

                new_distance = (
                        distance_map[current]
                        + edge.length
                )

                if new_distance < distance_map.get(
                        neighbour,
                        math.inf
                ):
                    distance_map[neighbour] = new_distance
                    previous[neighbour] = current

                    priority = (
                            new_distance
                            + distance(
                        neighbour.point,
                        goal.point
                    )
                    )

                    heapq.heappush(
                        queue,
                        (
                            priority,
                            next(counter),
                            neighbour
                        )
                    )

        path = []
        current = goal

        while current in previous:
            path.append(current)
            current = previous[current]

        path.append(start)

        return path[::-1]

    def to_dict(self):
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges]
        }

    @staticmethod
    def from_dict(data):
        graph = Graph()

        nodes, node_data = zip(*[
            Node.from_dict(n_dict)
            for n_dict in data["nodes"]
        ])

        edges = [
            Edge.from_dict(e_dict, nodes)
            for e_dict in data["edges"]
        ]

        graph.nodes = nodes
        graph.edges = edges

        for i, node in enumerate(graph.nodes):
            edge_ids = node_data[i]

            node.edges = [
                graph.edges[edge_id]
                for edge_id in edge_ids
            ]

        return graph


# Loading:

class Street:
    def __init__(self, name, points, width):
        self.name = name
        self.points = points
        self.width = width

    def to_dict(self):
        return {"name": self.name, "points": self.points, "width": self.width}

    @staticmethod
    def from_dict(data):
        return Street(data["name"], data["points"], data["width"])

def load_streets(path, convert_func=None):
    tree = ET.parse(path)
    root = tree.getroot()

    streets = []

    for street in root.findall("street"):
        name = street.get("name", f"Unknown Street {len(street)}")
        width = int(street.get("width", 1))

        if "Railroad" in name:
            continue

        points = []
        for p in street.find("points").findall("point"): # NOQA
            x = float(p.get("x")) # NOQA
            y = float(p.get("y")) # NOQA

            if convert_func:
                x, y = convert_func(x, y)

            points.append(( x, y ))

        streets.append(
            Street(
                name,
                points,
                width
            )
        )

    return streets


def build_graph(streets, tolerance=1.0, render_callback=None):
    print("Building Path-finding Graph... (This may take some time)")
    #
    # First create all segments
    #

    segments = []

    for street in streets:
        for a, b in zip(street.points, street.points[1:]):
            ax, ay = a
            bx, by = b

            dx = bx - ax
            dy = by - ay

            dst = math.hypot(dx, dy)

            # Number of segments needed
            n = max(1, math.ceil(dst / tolerance//2))

            cuts = [
                (
                    ax + dx * i / n,
                    ay + dy * i / n
                )
                for i in range(n + 1)
            ]

            segments.append({
                "a": a,
                "b": b,
                "street": street.name,
                "width": street.width,
                "cuts": cuts
            })


    #
    # Find intersections
    #

    for i, s1 in enumerate(segments):

        for j, s2 in enumerate(segments):

            if i >= j:
                continue

            # skip neighbouring segments
            if s1["street"] == s2["street"]:
                continue


            point = segment_intersection(
                s1["a"],
                s1["b"],
                s2["a"],
                s2["b"]
            )

            if point:
                s1["cuts"].append(point)
                s2["cuts"].append(point)


    #
    # Create graph
    #

    graph = Graph()


    for segment in segments:

        points = segment["cuts"]


        # Sort points along segment
        points.sort(
            key=lambda p:
                distance(segment["a"], p)
        )

        if render_callback:
            render_callback(points, (255, 0, 0))


        for a, b in zip(
            points,
            points[1:]
        ):

            na = graph.get_node(
                a,
                tolerance
            )

            nb = graph.get_node(
                b,
                tolerance
            )


            graph.add_edge(
                na,
                nb,
                segment["street"],
                segment["width"]
            )

        if render_callback:
            render_callback(points, (0, 255, 0))

    print(f"Generated Graph With {len(graph.nodes)} nodes")

    return graph