import traceback
from quart import Quart
import os
from dotenv import load_dotenv
from core import response
from modules.generation import generate_id, Action

load_dotenv()
app = Quart(__name__)

SESSION_ID = generate_id(Action.SESSION)

secret_key = os.getenv('SECRET_KEY')
debug = os.getenv('DEBUG') == 'True'


@app.errorhandler(500)
async def handle_500(error):
    traceback.print_exc()
    return response(error=True, error_msg={
        "msg": "Internal Server Error",
        "code": "INTERNAL_SERVER_ERROR"
    }), 500


if __name__ == '__main__':
    app.run(debug=debug)
