from bottle import Bottle, request, response, run, BaseRequest
import os
import json
from Object.route import *

app = Bottle()
host = str(os.getenv('API_HOST', '0.0.0.0'))
port = int(os.getenv('API_PORT', 8080))

BaseRequest.MEMFILE_MAX = 1024 * 1024 * 256

@app.hook('after_request')
def enable_cors():
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.content_type = 'application/json'

@app.error()
@app.error(404)
@app.error(405)
def error(error):
    response.content_type = 'application/json'
    return json.dumps({"err": "Internal error", "data": None})



if __name__ == '__main__':
    setuproute(app)
    run(app, host=host, port=port, debug=True )
