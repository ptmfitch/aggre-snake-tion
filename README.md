# Classic Arcade Game Snake with the MongoDB Aggregation Pipeline

This repo contains an implementation of the Classic Arcade Game using the MongoDB Aggregation Framework.

![Snake GIF](snake.gif)

# How to get started

Ensure you have python3 and virtualenv installed

```shell
git clone https://github.com/ptmfitch/aggre-snake-tion
cd aggre-snake-tion
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

Update the parameters in the `simulation.py` script:

```python
DB = "snake"
COLL = "grid"
TURN_BASED = False
SIZE_X = 5
SIZE_Y = 4
START_SIZE = 3
```

Then you can just start the program and point to a MongoDB instance of your choice:

```shell
python3.9 simulation.py "mongodb+srv://USERNAME:PASSWORD@CLUSTER_URI/?retryWrites=true&w=majority"
```

# Visualization

To see the game in action, I'm using a chart in MongoDB Atlas Charts that is setup like this: 

- Open Charts
- Click the dropdown on Add Dashboard
- Select "Import dashboard" and upload snake.charts from this repo
- Update the data set settings to your cluster
