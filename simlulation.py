import sys
from time import time, sleep

from pymongo import MongoClient, ASCENDING

# Of course we're using Python to make a Snake clone...

# TODO make this config a queryable document
DB = "snake"
COLL = "grid"
# Maximum grid size is 140 x 140
# Visualisations in Charts have a maximum document count of 20,000
SIZE_X = 5
SIZE_Y = 4
START_SIZE = 3
# Minimum refresh is 10
# Charts has a minimum refresh rate of 10 seconds
REFRESH_SECONDS = 20

# Global Stage: Set grid based on head, snake, and egg tiles
stage_set_grid = { '$set': {
  'grid': { '$map': {
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
            'then': 9
          }, {
            'case': { '$in': [ { 'x': '$$x', 'y': '$$y' }, '$body' ] },
            # Scale colour percentage based on head -> tail position
            'then': { '$subtract': [
              8, { '$multiply': [ { '$divide': [
                { '$indexOfArray': ['$body', {'x': '$$x', 'y': '$$y'}] },
                { '$size': '$body' }
              ] }, 2 ] }
            ] }
          }, {
            'case': { '$eq': [ { 'x': '$$x', 'y': '$$y' }, '$egg' ] },
            'then': 0
          } ],
          'default': 5
        } }
      }
    } }
  } }
} }

# Global Stage: Randomly set egg tile based on available tiles
stage_set_egg = { '$set': {
  'egg': { '$cond': {
    'if': { '$or': [ { '$eq': [ '$turn', 0 ] }, '$eaten' ] },
    'then': { '$let': {
      'vars': { 'avblTiles': { '$filter': {
        # Use $reduce to create flat array of all tiles in grid
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
        'as': 't',
        # Keep only tiles that aren't snake head or body
        'cond': { '$and': [
          { '$ne': [ '$$t', '$head' ] },
          { '$not': { '$in': [ '$$t', '$body' ] } }
        ] }
      } } },
      'in': { '$arrayElemAt': [
        '$$avblTiles',
        { '$floor': { '$multiply': [
          { '$rand': {} },
          { '$size': '$$avblTiles' }
        ] } }
      ] }
    } },
    'else': '$egg'
  } }
} }

# Global Stage: Merge documents into existing collection
stage_merge = { '$merge': COLL }


def init_grid(db):

  # TODO validate config, e.g. snake length < SIZE_X or SIZE Y

  print("Dropping existing collection")
  db.drop_collection(COLL)

  print("Creating a new collection")
  collection = db.create_collection(COLL)

  print("Inserting empty document into collection")
  collection.create_index([("turn", -1)])
  collection.insert_one({"turn": 0})

  # Stage 1: Set initial game metadata
  stage_set_metadata = { '$set': {
    'eaten': False,
    'alive': True,
    'turn': 0
  } }

  # Stage 2: Randomly set snake head tile anywhere on grid
  stage_set_head = { '$set': {
    'head': {
      # Example 1: Random Integer between 0 (inclusive) and N (exclusive)
      'x': { '$floor': { '$multiply': [ { '$rand': {} }, SIZE_X ] } },
      'y': { '$floor': { '$multiply': [ { '$rand': {} }, SIZE_Y ] } }
    } 
  } }

  # Stage 3: Randomly set snake direction based on available tiles
  # Four possible directions:
  #   0: Up (-y),
  #   1: Right (+x),
  #   2: Down (+y)
  #   3: Left (-x)
  stage_set_direction = { '$set': {
    'direction': { '$let': {
      'vars': { 'avblDirs': { '$filter': {
        'input': { '$range': [ 0, 4 ] },
        'as': 'd',
        'cond': { '$switch': { 'branches': [ {
          'case': { '$eq': [ '$$d', 0 ] },
          'then': { '$gte': [
            # Only need to check last element of snake body in each direction
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
        { '$floor': { '$multiply': [
          { '$rand': {} },
          { '$size': '$$avblDirs' }
        ] } }
      ] }
    } }
  } }

  # Stage 4: Set snake body tiles based on direction
  stage_set_body = { '$set': {
    'body': { '$map': {
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
  } }

  # Stage 5: Global set egg stage
  
  # Stage 6: Global set grid stage

  # Stage 7: Set turn increment
  stage_set_turn = { '$set': {
    'turn': { '$add': [ '$turn', 1 ] }
  } }

  # Stage 8: Global merge stage

  pipeline = [ stage_set_metadata,
               stage_set_head,
               stage_set_direction,
               stage_set_body,
               stage_set_egg,
               stage_set_grid,
               stage_set_turn,
               stage_merge ]

  start = time()
  collection.aggregate(pipeline)
  print('Grid init done in', round(time() - start, 2), 's')


def next_turn(db):

  # Stage 1: Match only alive games
  stage_match_alive = { '$match': { 'alive': True } }

  # Stage 2: Set snake new body (i.e. move and/or grow the snake)
  stage_set_body = { '$set': {
    'body': { '$cond': {
      'if': '$eaten',
      # If snake ate last turn, then grow body by prepending head
      'then': { '$concatArrays': [ [ '$head' ], '$body' ] },
      # Else move snake by prepending head and slicing off tail
      'else': { '$concatArrays': [
        [ '$head' ],
        { '$slice': [ 
          '$body', 0, { '$subtract': [ { '$size': '$body' }, 1 ] }
        ] }
      ] }
    } }
  } }

  # Stage 3: Set new direction (i.e. decide where to move next)
  stage_set_direction = { '$set': {
    'direction': { '$let': {
      # Narrow down choices of which direction to move in
      'vars': {
        # All available directions
        'avblDirs': { '$filter': {
          'input': { '$range': [ 0, 4 ] },
          'as': 'd',
          'cond': { '$switch': { 'branches': [ {
            'case': { '$eq': [ '$$d', 0 ] },
            'then': { '$and': [
              # Can't move to a tile where the snake body is
              { '$not': { '$in': [
                { 'x': '$head.x', 'y': { '$subtract': [ '$head.y', 1 ] } },
                '$body'
              ] } },
              # Can't move out of bounds
              { '$gte': [ { '$subtract': [ '$head.y', 1 ] }, 0 ] }
            ] }
          }, {
            'case': { '$eq': [ '$$d', 1 ] },
            'then': { '$and': [
              { '$not': { '$in': [
                { 'x': { '$add': [ '$head.x', 1 ] }, 'y': '$head.y' },
                '$body'
              ] } },
              { '$lt': [ { '$add': [ '$head.x', 1 ] }, SIZE_X ] }
            ] }
          }, {
            'case': { '$eq': [ '$$d', 2 ] },
            'then': { '$and': [
              { '$not': { '$in': [
                { 'x': '$head.x', 'y': { '$add': [ '$head.y', 1 ] } },
                '$body'
              ] } },
              { '$lt': [ { '$add': [ '$head.y', 1 ] }, SIZE_Y ] }
            ] }
          }, {
            'case': { '$eq': [ '$$d', 3 ] },
            'then': { '$and': [
              { '$not': { '$in': [
                { 'x': { '$subtract': [ '$head.x', 1 ] }, 'y': '$head.y' },
                '$body'
              ] } },
              { '$gte': [ { '$subtract': [ '$head.x', 1 ] }, 0 ] }
            ] }
          } ] } }
        } },
        # Directions that bring snake towards egg
        'eggDirs': { '$filter': {
          'input': { '$range': [ 0, 4 ] },
          'as': 'd',
          'cond': { '$switch': { 'branches': [ {
            'case': { '$eq': [ '$$d', 0 ] },
            'then': { '$gt': [ '$head.y', '$egg.y' ] }
          }, {
            'case': { '$eq': [ '$$d', 1 ] },
            'then': { '$lt': [ '$head.x', '$egg.x' ] }
          }, {
            'case': { '$eq': [ '$$d', 2 ] },
            'then': { '$lt': [ '$head.y', '$egg.y' ] }
          }, {
            'case': { '$eq': [ '$$d', 3 ] },
            'then': { '$gt': [ '$head.x', '$egg.x' ] }
          } ] } }
        } }
      },
      'in': { '$switch': {
        'branches': [ {
          # If there's only one direction, we have no choice
          'case': { '$eq': [ { '$size': '$$avblDirs' }, 1 ] },
          'then': { '$first': '$$avblDirs' }
        }, {
          # If the egg is still in the direction we're heading, keep going
          'case': { '$in': [
            '$direction', { '$setIntersection': [ '$$avblDirs', '$$eggDirs' ] }
          ] },
          'then': '$direction'
        }, {
          # Otherwise, if there's an available move towards the egg, do that
          'case': { '$gt': [
            { '$size': { '$setIntersection': [ '$$avblDirs', '$$eggDirs' ] } },
            0
          ] },
          # TODO add heuristic for how to decide which way to choose here
          'then': { '$arrayElemAt': [
            { '$setIntersection': [ '$$avblDirs', '$$eggDirs' ] },
            { '$floor': { '$multiply': [
              { '$rand': {} },
              { '$size': { '$setIntersection': [ '$$avblDirs', '$$eggDirs' ] } }
            ] } }
          ] }
        }, {
          # Keep going the way we're heading if available
          'case': { '$in': [ '$direction', '$$avblDirs' ] },
          'then': '$direction'
        } ],
        # Default is choose a random direction
        # TODO add heuristic for how to decide which way to choose here
        'default': { '$arrayElemAt': [
          '$$avblDirs',
          { '$floor': { '$multiply': [
            { '$rand': {} }, { '$size': '$$avblDirs' }
          ] } }
        ] }
      } }
    } }
  } }

  # Stage 4: Set new head based on direction chosen
  stage_set_head = { '$set': {
    'head': { '$switch': { 'branches': [ { 
      'case': { '$eq': [ '$direction', 0 ] },
      'then': { 
        'x': '$head.x',
        'y': { '$subtract': [ '$head.y', 1 ] } 
      }
    }, {
      'case': { '$eq': [ '$direction', 1 ] },
      'then': { 
        'x': { '$add': [ '$head.x', 1 ] },
        'y': '$head.y' 
      }
    }, {
      'case': { '$eq': [ '$direction', 2 ] },
      'then': { 
        'x': '$head.x',
        'y': { '$add': [ '$head.y', 1 ] } 
      }
    }, {
      'case': { '$eq': [ '$direction', 3 ] },
      'then': { 
        'x': { '$subtract': [ '$head.x', 1 ] },
        'y': '$head.y' 
      }
    } ] } }
  } }

  # Stage 5: Very simply, set eaten True if head on egg tile
  stage_set_eaten = { '$set': { 'eaten': { '$eq': [ '$egg', '$head' ] } } }

  # Stage 6: Global set egg stage

  # Stage 7: Global set grid stage

  # Stage 8: Global merge stage

  pipeline = [ stage_match_alive,
               stage_set_body,
               stage_set_direction,
               stage_set_head,
               stage_set_eaten,
               stage_set_egg,
               stage_set_grid,
               stage_merge ]
  
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
    # while(True):
    #   input('Hit Enter for the next generation...')
    #   next_turn(db)
    while(True): # TODO game win or loss condition
      sleep(REFRESH_SECONDS)
      next_turn(db)

# TODO display in plotly and allow scrolling through history
