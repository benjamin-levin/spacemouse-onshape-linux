import asyncio
import logging
import struct
from pathlib import Path

import typer
import uvicorn
from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import StreamingResponse, HTMLResponse
from rich.logging import RichHandler

from spacenav_ws.controller import create_mouse_controller
from spacenav_ws.spacenav import from_message, get_async_spacenav_socket_reader
from spacenav_ws.wamp import WampSession

# TODO: This handler isn't used for the uvicorn logs and I can't be bothered finding the magic logging incantations to make it so.
logging.basicConfig(level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler()])

ORIGINS = [
    "https://127.51.68.120",
    "https://127.51.68.120:8181",
    "https://3dconnexion.com",
]


def is_allowed_origin(origin: str | None) -> bool:
    if not origin:
        return False
    if origin in ORIGINS:
        return True
    return origin.startswith("https://") and origin.endswith(".onshape.com")

CERT_FILE = Path(__file__).parent / "certs" / "ip.crt"
KEY_FILE = Path(__file__).parent / "certs" / "ip.key"

cli = typer.Typer()
app = FastAPI()


@app.middleware("http")
async def add_private_network_headers(request: Request, call_next):
    if request.method == "OPTIONS" and request.url.path == "/3dconnexion/nlproxy":
        response = Response(status_code=204)
    else:
        response = await call_next(request)
    origin = request.headers.get("origin")
    if is_allowed_origin(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = request.headers.get("access-control-request-headers", "*")
    if request.headers.get("access-control-request-private-network") == "true":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


@app.options("/3dconnexion/nlproxy")
async def options_info(request: Request):
    response = Response(status_code=204)
    origin = request.headers.get("origin")
    if is_allowed_origin(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = request.headers.get("access-control-request-headers", "*")
    if request.headers.get("access-control-request-private-network") == "true":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


@app.get("/3dconnexion/nlproxy")
async def get_info():
    """HTTP info endpoint for the 3Dconnexion client. Returns which port the WAMP bridge will use and its version."""
    return {"port": 8181, "version": "1.4.8.21486"}


@app.get("/")
def homepage():
    """Tiny bit of HTML that displays mouse movement data"""
    html = """
    <html>
        <body>
            <h1>Mouse Stream</h1>
            <p>Move your spacemouse and motion data should appear here!</p>
            <pre id="output"></pre>
            <script>
                const evtSource = new EventSource("/events");
                const maxLines = 30;
                const lines = [];

                evtSource.onmessage = function(event) {
                    lines.push(event.data);
                    if (lines.length > maxLines) {lines.shift()}
                    document.getElementById("output").textContent = lines.join("\\n");
                };
            </script>
        </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=200)


async def get_mouse_event_generator():
    reader, _ = await get_async_spacenav_socket_reader()
    while True:
        mouse_event = await reader.readexactly(32)
        nums = struct.unpack("iiiiiiii", mouse_event)
        event_data = from_message(list(nums))
        yield f"data: {event_data}\n\n"  # <- SSE format


@app.get("/events")
async def event_stream():
    """Stream mouse motion data"""
    return StreamingResponse(get_mouse_event_generator(), media_type="text/event-stream")


@app.websocket("/")
async def nlproxy(ws: WebSocket):
    """This is the websocket that webapplications should connect to for mouse data"""
    wamp_session = WampSession(ws)
    spacenav_reader, _ = await get_async_spacenav_socket_reader()
    ctrl = await create_mouse_controller(wamp_session, spacenav_reader)
    # TODO, better error handling then just dropping the websocket disconnect on the floor?
    async with asyncio.TaskGroup() as tg:
        tg.create_task(ctrl.start_mouse_event_stream(), name="mouse-input")
        tg.create_task(ctrl.start_control_loop(), name="mouse-control")
        tg.create_task(ctrl.wamp_state_handler.start_wamp_message_stream(), name="wamp")


@cli.command()
def serve(host: str = "127.51.68.120", port: int = 8181, hot_reload: bool = False):
    """Start the server that sends spacenav to browser based applications like onshape"""
    logging.warning(f"Navigate to: https://{host}:{port} You should be prompted to add the cert as an exception to your browser!!")
    uvicorn.run(
        "spacenav_ws.main:app", host=host, port=port, ws="auto", ssl_certfile=CERT_FILE, ssl_keyfile=KEY_FILE, log_level="info", reload=hot_reload
    )


@cli.command()
def read_mouse():
    """This echos the output from the spacenav socket, usefull for checking if things are working under the hood"""

    async def read_mouse_stream():
        logging.info("Start moving your mouse!")
        async for event in get_mouse_event_generator():
            logging.info(event.strip())

    asyncio.run(read_mouse_stream())


if __name__ == "__main__":
    cli()
