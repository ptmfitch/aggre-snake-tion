import sys
from time import time, sleep

from pymongo import MongoClient, ASCENDING

# TODO make this config a queryable document
DB = "snake"
COLL = "grid"
# Maximum grid size is 140 x 140
# Visualisations in Charts have a maximum document count of 20,000
SIZE_X = 80
SIZE_Y = 50
START_SIZE = 3
# Minimum refresh is 10
# Charts has a minimum refresh rate of 10 seconds
REFRESH_SECONDS = 10


def init_grid(db):

  # TODO validate config, e.g. snake length < SIZE_X or SIZE Y

  print("Dropping existing collection")
  db.drop_collection(COLL)

  print("Creating a new collection")
  collection = db.create_collection(COLL)

  print("Inserting empty document into collection")
  collection.create_index([("turn", -1)])
  collection.insert_one({"turn": 0})

  pipeline = [ {
    # Stage 1: Randomly set the snake's head tile anywhere on the grid
    '$set': { 'head': {
      # Example 1: Random Integer between 0 (inclusive) and N (exclusive)
      'x': { '$floor': { '$multiply': [ { '$rand': {} }, SIZE_X ] } },
      'y': { '$floor': { '$multiply': [ { '$rand': {} }, SIZE_Y ] } }
    } }
  }, {
    # Stage 2: Randomly set the snake's direction based on available tiles
    # Four possible directions:
    #   0: Up (-y),
    #   1: Right (+x),
    #   2: Down (+y)
    #   3: Left (-x)
    '$set': { 'direction': { '$let': {
      'vars': { 'avblDirs': { '$filter': {
        'input': { '$range': [ 0, 4 ] },
        'as': 'd',
        'cond': { '$switch': { 'branches': [ {
          'case': { '$eq': [ '$$d', 0 ] },
          'then': { '$gte': [
            # Only need to check last element of snake in each direction
            # e.g. for up we check head.y - (snake size - 1) > 0 etc.
            { '$subtract': [ '$head.y', { '$subtract': [ START_SIZE, 1 ] } ] },
            0
          ] }
        }, {
          'case': { '$eq': [ '$$d', 1 ] },
          'then': { '$lt': [
            { '$add': [ '$head.x', { '$subtract': [ START_SIZE, 1 ] } ] },
            SIZE_X
          ] }
        }, {
          'case': { '$eq': [ '$$d', 2 ] },
          'then': { '$lt': [
            { '$add': [ '$head.y', { '$subtract': [ START_SIZE, 1 ] } ] },
            SIZE_Y
          ] }
        }, {
          'case': { '$eq': [ '$$d', 3 ] },
          'then': { '$gte': [
            { '$subtract': [ '$head.x', { '$subtract': [ START_SIZE, 1 ] } ] },
            0
          ] }
        } ] } }
      } } },
      # Example 2: Random Element from an Array
      'in': { '$arrayElemAt': [
        '$$avblDirs',
        { '$floor': { '$multiply': [ { '$rand': {} }, { '$size': '$$avblDirs' } ] } }
      ] }
    } } }
  }, {
    # Stage 3: Set the snake's body tiles (array of {x, y} objects) based on its direction
    '$set': { 'snake': { '$concatArrays': [
        [ '$head' ],
        { '$map': {
          'input': { '$range': [ 1, START_SIZE ] },
          'as': 'offset',
          'in': { '$switch': { 'branches': [ { 
            'case': { '$eq': [ '$direction', 0 ] },
            'then': { 
              'x': '$head.x',
              'y': { '$subtract': [ '$head.y', '$$offset' ] } 
            }
          }, {
            'case': { '$eq': [ '$direction', 1 ] },
            'then': { 
              'x': { '$add': [ '$head.x', '$$offset' ] },
              'y': '$head.y' 
            }
          }, {
            'case': { '$eq': [ '$direction', 2 ] },
            'then': { 
              'x': '$head.x',
              'y': { '$add': [ '$head.y', '$$offset' ] } 
            }
          }, {
            'case': { '$eq': [ '$direction', 3 ] },
            'then': { 
              'x': { '$subtract': [ '$head.x', '$$offset' ] },
              'y': '$head.y' 
            }
          } ] } }
        } }
      ] } }
  }, {
    # Stage 4: Randomly set the egg tile based on available tiles
    '$set': { 'egg': { '$let': {
      'vars': { 'avblTiles': { '$filter': {
        'input': { '$reduce': {
          'input': { '$map': {
            'input': { '$range': [0, SIZE_X] },
            'as': 'x',
            'in': { '$map': {
              'input': { '$range': [0, SIZE_Y] },
              'as': 'y',
              'in': { 'x': '$$x', 'y': '$$y' }
            } }
          } },
          'initialValue': [],
          'in': { '$concatArrays': [ '$$value', '$$this' ] }
        } },
        'as': 'tile',
        'cond': { '$not': { '$in': [ '$$tile', '$snake' ] } }
      } } },
      'in': { '$arrayElemAt': [
        '$$avblTiles',
        { '$floor': { '$multiply': [ { '$rand': {} }, { '$size': '$$avblTiles' } ] } }
      ] }
    } } }
  }, {
    # Stage 5: Set the grid based on snake and egg tiles
    '$set': { 'grid': { '$map': {
      'input': { '$range': [ 0, SIZE_X ] },
      'as': 'x',
      'in': { '$map': {
        'input': { '$range': [ 0, SIZE_Y ] },
        'as': 'y',
        'in': {
          'x': '$$x',
          'y': '$$y',
          'colour': { '$switch': {
            'branches': [ {
              'case': { '$eq': [ { 'x': '$$x', 'y': '$$y' }, '$head' ] },
              'then': 0
            }, {
              'case': { '$in': [ { 'x': '$$x', 'y': '$$y' }, '$snake' ] },
              'then': 1
            }, {
              'case': { '$eq': [ { 'x': '$$x', 'y': '$$y' }, '$egg' ] },
              'then': 2
            } ],
            'default': 3
          } }
        }
      } }
    } } }
  }, {
    '$merge': COLL
  } ]
  start = time()
  collection.aggregate(pipeline)
  print('Grid init done in', round(time() - start, 2), 's')


def next_turn(db):
  pipeline = [
    # Grab the most recent turn document
    { '$sort': { 'turn': -1 } },
    { '$limit': 1 },
    # Snake movement logic, effectively promote the last
    # element to a new head, moving towards the egg
    { '$set': {
      # Increment the turn number while we're here
      'turn': { '$add': [ '$turn', 1 ] },
      # Set the new values for the snake array
      'snake': { '$let': {
        'vars': {
          # Borrowing some Seq names from Scala
          # HTT (head, tail)
          # IIL (init, last)
          # NB keep last if we've eaten an egg last turn
          'head': { '$first': '$snake' },
          'init': { '$cond': {
            'if': '$eaten',
            'then': '$snake',
            'else': { '$slice': [ 
              '$snake',
              0, { '$subtract': [ { '$size': '$snake' }, 1 ] }
            ] }
          } }
        },
        'in': { '$switch': {
          'branches': [ {
            # Attempt to move towards negative x (left)
            'case': { '$and': [
              # Check the egg is in this direction
              { '$gt': [ '$$head.x', '$egg.x' ] },
              # Check the tile to move to isn't part of the snake
              { '$not': { '$in': [ { 'x': { '$subtract': [ '$$head.x', 1 ] }, 'y': '$$head.y' }, '$$init' ] } },
              # Check the tile to move to isn't outside of the grid
              { '$gte': [ { '$subtract': [ '$$head.x', 1 ] }, 0 ] }
            ] },
            # Add the new head onto the init array to form the new snake
            'then': { '$concatArrays': [ [ { 'x': { '$subtract': [ '$$head.x', 1 ] }, 'y': '$$head.y' } ], '$$init' ] }
          }, {
            # Attempt to move towards positive x (right)
            'case': { '$and': [
              { '$lt': [ '$$head.x', '$egg.x' ] },
              { '$not': { '$in': [ { 'x': { '$add': [ '$$head.x', 1 ] }, 'y': '$$head.y' }, '$$init' ] } },
              { '$lt': [ { '$add': [ '$$head.x', 1 ] }, SIZE_X ] }
            ] },
            'then': { '$concatArrays': [ [ { 'x': { '$add': [ '$$head.x', 1 ] }, 'y': '$$head.y' } ], '$$init' ] }
          }, {
            # Attempt to move towards negative y (up)
            'case': { '$and': [
              { '$gt': [ '$$head.y', '$egg.y' ] },
              { '$not': { '$in': [ { 'x': '$$head.x', 'y': { '$subtract': [ '$$head.y', 1 ] } }, '$$init' ] } },
              { '$gte': [ { '$subtract': [ '$$head.y', 1 ] }, 0 ] }
            ] },
            'then': { '$concatArrays': [ [ { 'x': '$$head.x', 'y': { '$subtract': [ '$$head.y', 1 ] } } ], '$$init' ] },
          }, {
            # Attempt to move towards positive y (down)
            'case': { '$and': [
              { '$lt': [ '$$head.y', '$egg.y' ] },
              { '$not': { '$in': [ { 'x': '$$head.x', 'y': { '$add': [ '$$head.y', 1 ] } }, '$$init' ] } },
              { '$lt': [ { '$add': [ '$$head.y', 1 ] }, SIZE_Y ] }
            ] },
            'then': { '$concatArrays': [ [ { 'x': '$$head.x', 'y': { '$add': [ '$$head.y', 1 ] } } ], '$$init' ] }
          } ] # TODO hail mary movement logic, bias towards current facing direction (create a save point when this happens), tune the hyperparameters
        } }
      } }
    } },
    # Eat the egg logic
    { '$set': { 'eaten': { '$eq': [ '$egg', { '$first': '$snake' } ] } } },
    { '$set': { 'egg': { '$cond': {
      'if': '$eaten',
      'then': { '$let': {
        'vars': { 'freeTiles': { '$filter': {
          'input': { '$reduce': {
            'input': { '$map': {
              'input': { '$range': [0, SIZE_X] },
              'as': 'x',
              'in': { '$map': {
                'input': { '$range': [0, SIZE_Y] },
                'as': 'y',
                'in': { 'x': '$$x', 'y': '$$y' }
              } }
            } },
            'initialValue': [],
            'in': { '$concatArrays': [ '$$value', '$$this' ] }
          } },
          'as': 'tile',
          'cond': { '$not': { '$in': [ '$$tile', '$snake' ] } }
        } } },
        'in': { '$arrayElemAt': [
          '$$freeTiles',
          { '$floor': { '$multiply': [ { '$rand': {} }, { '$size': '$$freeTiles' } ] } }
        ] }
      } },
      'else': '$egg'
    } } } },
    # Regenerate the grid
    { '$set': {
      # Construct a grid to display in charts (requires a double $unwind)
      'grid': { '$map': {
        'input': { '$range': [ 0, SIZE_X ] },
        'as': 'x',
        'in': { '$map': {
          'input': { '$range': [ 0, SIZE_Y ] },
          'as': 'y',
          'in': {
            'x': '$$x',
            'y': '$$y',
            'colour': { '$cond': {
              'if': { '$in': [ { 'x': '$$x', 'y': '$$y' }, '$snake' ] },
              'then': 0,
              'else': { '$cond': {
                'if': { '$eq': [ { 'x': '$$x', 'y': '$$y' }, '$egg' ] },
                'then': 1,
                'else': 2
              } }
            } }
          }
        } }
      } }
    } },
    { '$merge': COLL }
  ]
  start = time()
  db.get_collection(COLL).aggregate(pipeline)
  print('Next turn calculated in', round(time() - start, 2), 's')



def check_mongodb_uri():
  if len(sys.argv) != 2:
    print('MongoDB URI is missing in cmd line arg 1.')
    exit(1)


def get_mongodb_client(uri):
    return MongoClient(uri)


if __name__ == '__main__':
    check_mongodb_uri()
    client = get_mongodb_client(sys.argv[1])
    db = client.get_database(DB)
    init_grid(db)
    while(True):
      input('Hit Enter for the next generation...')
      next_turn(db)
    # while(True): # TODO game win or loss condition
    #   sleep(REFRESH_SECONDS)
    #   next_turn(db)

# TODO display in plotly and allow scrolling through history
