import sys
from time import time, sleep

from pymongo import MongoClient, ASCENDING

# TODO make this config a queryable document
DB = "snake"
COLL = "grid"
SIZE_X = 5
SIZE_Y = 5
SNAKE_START_SIZE = 3
REFRESH_SECONDS = 3 # Fastest refresh in charts is every 10s


def init_grid(db):

  print("Dropping existing collection")
  db.drop_collection(COLL)

  print("Creating a new collection")
  collection = db.create_collection(COLL)

  print("Inserting empty document into collection")
  collection.create_index([("turn", -1)])
  collection.insert_one({"turn": 0})

  pipeline = [
    { '$set': {
      # Randomly place the first egg anywhere
      'egg': {
        'x': { '$floor': { '$multiply': [ { '$rand': {} }, SIZE_X ] } },
        'y': { '$floor': { '$multiply': [ { '$rand': {} }, SIZE_Y ] } }
      }
    } }, 
    { '$set': {
      'snake': {
        '$let': {
          'vars': {
            # The snake always starts pointing left (negative x),
            # so needs to be at least SNAKE_START_SIZE away from
            # the right hand edge
            # TODO improve by using a random selection from a valid array
            # of tile windows
            'x': { '$floor': { '$multiply': [ 
              { '$rand': {} }, 
              { '$subtract': [ SIZE_X, SNAKE_START_SIZE ] }
            ] } },
            # To avoid the snake spawning on top of the egg, the
            # initial y value should be on the opposite end
            'y': {
              '$cond': {
                'if': { '$gt': [ '$egg.y', { '$divide': [ SIZE_Y, 2 ] } ] },
                'then': { '$floor': { '$multiply': [ 
                  { '$rand': {} },
                  { '$floor': { '$divide': [ SIZE_Y, 2 ] } }
                ] } },
                'else': { '$add': [
                  { '$floor': { '$multiply': [ 
                    { '$rand': {} },
                    { '$divide': [ SIZE_Y, 2 ] } 
                  ] } },
                  { '$floor': { '$divide': [ SIZE_Y, 2 ] } }
                ] }
              }
            }
          },
          # The snake will start with its head to the left and
          # tail extending to the right
          'in': {
            '$map': {
              'input': { '$range': [0, SNAKE_START_SIZE] },
              'in': {
                'x': { '$add': [ '$$x', '$$this' ] },
                'y': '$$y'
              }
            }
          }
        }
      }
    } },
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
          } ]
        } }
      } }
    } },
    # Eat the egg logic
    { '$set': { 'eaten': { '$eq': [ '$egg', { '$first': '$snake' } ] } } },
    { '$set': { 'egg': { '$cond': {
      'if': '$eaten',
      'then': { '$let': {
        'vars': {
          'freeSpaces': { '$filter': {
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
          } }
        },
        'in': { '$arrayElemAt': [
          '$$freeSpaces',
          { '$floor': { '$multiply': [
            { '$rand': {} },
            { '$size': '$$freeSpaces' }
          ] } }
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
