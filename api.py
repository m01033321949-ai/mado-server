
import sys
import os
# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from server import app
import serverless_wsgi

def handler(event, context):
    return serverless_wsgi.handle_request(app, event, context)
