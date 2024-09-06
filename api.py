import asyncio
import traceback
import uuid
from quart import request
import os
from core import response
from utils.generation import generate_id, Action
from supabase import create_client, Client
from supabase.client import ClientOptions
from core import app


SESSION_ID = generate_id(Action.SESSION)

debug = os.getenv('DEBUG') == 'True'
supabase_url: str = os.environ.get("SUPABASE_URL")  # type: ignore
supabase_key: str = os.environ.get("SUPABASE_KEY")  # type: ignore
supabase: Client = create_client(
    supabase_url, supabase_key,
    options=ClientOptions(
        storage_client_timeout=10
    )
)


@app.errorhandler(500)
async def handle_500(error):
    traceback.print_exc()
    return response(error=True, error_msg={
        "msg": "Internal Server Error",
        "code": "INTERNAL_SERVER_ERROR"
    }), 500


@app.route('/generate_upload_url', methods=['POST'])
async def generate_upload_url():
    data = await request.get_json()

    file_name = data.get('file_name', '')
    random_file_name = f"user/{uuid.uuid4()}.{file_name}"

    upload_url = (
        supabase.storage.from_('default')
        .create_signed_upload_url(random_file_name)
    )

    return response(data={
        "upload_url": upload_url['signed_url'],
        "file_url": (
            f"{supabase_url}/storage/v1/object/public/default/" +
            f"{random_file_name}"
        ),
        "file_name": random_file_name
    }), 200


async def main_task():
    quart_task = asyncio.create_task(
        app.run_task(
            debug=debug, port=6169,
            # certfile="cert.pem",
            # keyfile="key.pem"
        )
    )
    await asyncio.gather(quart_task)


if __name__ == '__main__':
    asyncio.run(main_task())
