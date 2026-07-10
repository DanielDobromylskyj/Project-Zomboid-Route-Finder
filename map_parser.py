import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw

# Load XML
tree = ET.parse("data/streets.xml")
root = tree.getroot()

streets = []

# Collect all coordinates
min_x = float("inf")
min_y = float("inf")
max_x = float("-inf")
max_y = float("-inf")

for street in root.findall("street"):
    width = int(street.get("width", 1))

    pts = []
    for p in street.find("points").findall("point"):
        x = float(p.get("x"))
        y = float(p.get("y"))
        pts.append((x, y))

        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x)
        max_y = max(max_y, y)

    streets.append((pts, width))

# Image settings
padding = 20

img_width = int(max_x - min_x + 2 * padding)
img_height = int(max_y - min_y + 2 * padding)

# Create black image
img = Image.new("L", (img_width, img_height), 0)
draw = ImageDraw.Draw(img)

# Draw streets in white
for pts, width in streets:
    shifted = [
        (x - min_x + padding, y - min_y + padding)
        for x, y in pts
    ]
    if len(shifted) >= 2:
        draw.line(shifted, fill=255, width=width)

img.save("roads.png")
print("Saved roads.png")