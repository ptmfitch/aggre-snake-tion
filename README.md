# Classic Arcade Game Snake with the MongoDB Aggregation Pipeline

This repo contains an implementation of the Classic Arcade Game using the MongoDB Aggregation Framework.

# How to get started

Update the parameters in the `simulation.py` program:

```python
DB = "snake"
COLL = "grid"
SIZE_X = 5
SIZE_Y = 4
START_SIZE = 3
```

Then you can just start the program and point to a MongoDB instance of your choice:

```shell
python3.9 simulation.py "mongodb+srv://USER:PASSWORD@CLUSTER.mongodb.net/"
```

# Visualization

To see the game of life in action, I'm using a chart in MongoDB Atlas Charts that is setup like this: 

- Chart Type: Heatmap
- X Axis: "x"
- Y Axis: "y"
- Intensity: "alive" with Aggregate "SUM"

In the `Customize` tab, I selected the back & white color palette.
