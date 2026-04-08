import asyncio
import logging
import struct
import time
from typing import Any

import numpy as np
from scipy.spatial import transform

from spacenav_ws.spacenav import MotionEvent, ButtonEvent, from_message
from spacenav_ws.wamp import WampSession, Prefix, Call, Subscribe, CallResult

MOTION_DEADZONE = np.array([35.0, 35.0, 35.0], dtype=np.float32)
ROTATION_DEADZONE = np.array([55.0, 55.0, 55.0], dtype=np.float32)
RAW_SATURATION = 350.0
TRANSLATION_CURVE = 1.55
ROTATION_CURVE = 1.35
DOMINANT_RATIO = 1.2
SMOOTHING_ALPHA = 0.82
TRANSLATION_SPEED = 2.0
ROTATION_SPEED_DEG = 240.0
ZOOM_SPEED = 1.6
STATE_REFRESH_INTERVAL = 0.2
CONTROL_HZ = 144.0
MOTION_STALE_TIMEOUT = 0.04


class Mouse3d:
    """This bad boy doesn't do a damn thing right now!"""

    def __init__(self):
        self.id = "mouse0"
        logging.info('Initialized 3d mouse stub "%s"', self.id)


class Controller:
    """Manage shared state and event streaming between a local 3D mouse and a remote client.

    This class subscribes clients over WAMP, tracks focus/subscription state,
    reads raw 3D mouse data from an asyncio.StreamReader, and forwards
    MotionEvent/ButtonEvent updates back to the client via RPC. It also
    provides utility methods for affine‐pivot calculations and generic
    remote_read/write operations.

    Args:
        reader (asyncio.StreamReader):
            Asynchronous stream reader for receiving raw 3D mouse packets.
        _ (Mouse3d):
            Doesn't do anything.. things should be restructured so that it does probably.
        wamp_state_handler (WampSession):
            WAMP session handler that manages subscriptions and RPC calls.
        client_metadata (dict):
            Metadata about the connected client (e.g. its name and capabilities).

    Attributes:
        id (str):
            Unique identifier for this controller instance (defaults to "controller0").
        client_metadata (dict):
            Same as the constructor arg: information about the client.
        reader (asyncio.StreamReader):
            Stream reader for incoming mouse event bytes.
        wamp_state_handler (WampSession):
            WAMP session object for subscribing and remote RPC.
        subscribed (bool):
            True once the client has subscribed to this controller’s URI.
        focus (bool):
            True when this controller is in focus and should send events.
    """

    def __init__(self, reader: asyncio.StreamReader, _: Mouse3d, wamp_state_handler: WampSession, client_metadata: dict):
        self.id = "controller0"
        self.client_metadata = client_metadata
        self.reader = reader
        self.wamp_state_handler = wamp_state_handler

        self.wamp_state_handler.wamp.subscribe_handlers[self.controller_uri] = self.subscribe
        self.wamp_state_handler.wamp.call_handlers["wss://127.51.68.120/3dconnexion#update"] = self.client_update

        self.subscribed = False
        self.focus = False
        self.filtered_trans = np.zeros(3, dtype=np.float32)
        self.filtered_rot = np.zeros(3, dtype=np.float32)
        self.cached_model_extents: np.ndarray | None = None
        self.cached_view_extents: np.ndarray | None = None
        self.cached_affine: np.ndarray | None = None
        self.cached_perspective: bool | None = None
        self.last_state_refresh = 0.0
        self.latest_motion: MotionEvent | None = None
        self.latest_motion_at = 0.0
        self.motion_lock = asyncio.Lock()
        self.button_queue: asyncio.Queue[ButtonEvent] = asyncio.Queue()
        self.needs_resync = True

    async def subscribe(self, msg: Subscribe):
        """When a subscription request for self.controller_uri comes in we start broadcasting!"""
        logging.info("handling subscribe %s", msg)
        self.subscribed = True
        self.focus = True

    async def client_update(self, controller_id: str, args: dict[str, Any]):
        # TODO Maybe use some more of this data that the client sends our way?
        logging.debug("client update for '%s': %s", controller_id, args)
        if (focus := args.get("focus")) is not None:
            self.focus = focus

    @property
    def controller_uri(self) -> str:
        return f"wss://127.51.68.120/3dconnexion3dcontroller/{self.id}"

    async def remote_write(self, *args):
        logging.debug("remote_write(%s)", args[0] if args else "")
        return await self.wamp_state_handler.client_rpc(self.controller_uri, "self:update", *args)

    async def remote_read(self, *args):
        logging.debug("remote_read(%s)", args[0] if args else "")
        return await self.wamp_state_handler.client_rpc(self.controller_uri, "self:read", *args)

    async def start_mouse_event_stream(self):
        """Read raw events and keep only the newest motion sample."""
        logging.info("Starting the mouse input stream")
        while True:
            mouse_event = await self.reader.read(32)
            if not (self.focus and self.subscribed):
                continue

            nums = struct.unpack("iiiiiiii", mouse_event)
            event = from_message(list(nums))
            if self.client_metadata["name"] not in ["Onshape", "WebThreeJS Sample"]:
                logging.warning("Unknown client! Cannot send mouse events, client_metadata:%s", self.client_metadata)
                continue

            if isinstance(event, ButtonEvent):
                await self.button_queue.put(event)
            else:
                async with self.motion_lock:
                    if self.in_deadzone(event):
                        self.latest_motion = None
                        self.latest_motion_at = time.monotonic()
                        self.filtered_trans.fill(0.0)
                        self.filtered_rot.fill(0.0)
                        self.cached_affine = None
                        self.cached_view_extents = None
                        self.cached_perspective = None
                        self.last_state_refresh = 0.0
                        self.needs_resync = True
                    else:
                        self.latest_motion = event
                        self.latest_motion_at = time.monotonic()

    async def start_control_loop(self):
        """Drive Onshape at a fixed cadence using only the latest state."""
        logging.info("Starting the control loop at %.1f Hz", CONTROL_HZ)
        tick = 1.0 / CONTROL_HZ
        last_tick = time.monotonic()

        while True:
            await asyncio.sleep(tick)
            if not (self.focus and self.subscribed):
                continue

            now = time.monotonic()
            dt = float(np.clip(now - last_tick, 0.001, 0.05))
            last_tick = now

            while not self.button_queue.empty():
                await self.update_client(await self.button_queue.get())

            async with self.motion_lock:
                event = self.latest_motion
                event_age = now - self.latest_motion_at if event is not None else 0.0

                if event is not None and event_age > MOTION_STALE_TIMEOUT:
                    self.latest_motion = None
                    event = None
                    self.filtered_trans.fill(0.0)
                    self.filtered_rot.fill(0.0)
                    self.cached_affine = None
                    self.cached_view_extents = None
                    self.cached_perspective = None
                    self.last_state_refresh = 0.0
                    self.needs_resync = True

            if event is None:
                continue

            await self.update_client(
                MotionEvent(
                    x=event.x,
                    y=event.y,
                    z=event.z,
                    pitch=event.pitch,
                    yaw=event.yaw,
                    roll=event.roll,
                    period=int(dt * 1000.0),
                )
            )

    @staticmethod
    def get_affine_pivot_matrices(model_extents):
        min_pt = np.array(model_extents[0:3], dtype=np.float32)
        max_pt = np.array(model_extents[3:6], dtype=np.float32)
        pivot = (min_pt + max_pt) * 0.5

        pivot_pos = np.eye(4, dtype=np.float32)
        pivot_pos[3, :3] = pivot
        pivot_neg = np.eye(4, dtype=np.float32)
        pivot_neg[3, :3] = -pivot
        return pivot_pos, pivot_neg

    @staticmethod
    def apply_deadzone_and_curve(vec: np.ndarray, deadzone: np.ndarray, exponent: float) -> np.ndarray:
        abs_vec = np.abs(vec)
        active = abs_vec > deadzone
        if not np.any(active):
            return np.zeros_like(vec)

        scaled = np.zeros_like(vec)
        scaled[active] = (abs_vec[active] - deadzone[active]) / (RAW_SATURATION - deadzone[active])
        scaled = np.clip(scaled, 0.0, 1.0)
        curved = np.power(scaled, exponent)
        return np.sign(vec) * curved

    @staticmethod
    def apply_dominant_axis(vec: np.ndarray) -> np.ndarray:
        abs_vec = np.abs(vec)
        max_idx = int(np.argmax(abs_vec))
        max_val = abs_vec[max_idx]
        if max_val <= 0.0:
            return vec
        second = float(np.partition(abs_vec, -2)[-2]) if len(abs_vec) > 1 else 0.0
        if second > 0.0 and max_val < second * DOMINANT_RATIO:
            return vec

        dom = np.zeros_like(vec)
        dom[max_idx] = vec[max_idx]
        return dom

    def process_motion(self, event: MotionEvent) -> tuple[np.ndarray, np.ndarray, float]:
        raw_trans = np.array([event.x, event.y, event.z], dtype=np.float32)
        raw_rot = np.array([event.pitch, event.yaw, event.roll], dtype=np.float32)

        trans = self.apply_deadzone_and_curve(raw_trans, MOTION_DEADZONE, TRANSLATION_CURVE)
        rot = self.apply_deadzone_and_curve(raw_rot, ROTATION_DEADZONE, ROTATION_CURVE)

        self.filtered_trans = (1.0 - SMOOTHING_ALPHA) * self.filtered_trans + SMOOTHING_ALPHA * trans
        self.filtered_rot = (1.0 - SMOOTHING_ALPHA) * self.filtered_rot + SMOOTHING_ALPHA * rot

        dt = float(np.clip(event.period / 1000.0, 0.001, 0.05))
        return self.filtered_trans.copy(), self.filtered_rot.copy(), dt

    @staticmethod
    def in_deadzone(event: MotionEvent) -> bool:
        raw_trans = np.abs(np.array([event.x, event.y, event.z], dtype=np.float32))
        raw_rot = np.abs(np.array([event.pitch, event.yaw, event.roll], dtype=np.float32))
        return bool(np.all(raw_trans <= MOTION_DEADZONE) and np.all(raw_rot <= ROTATION_DEADZONE))

    async def refresh_state(self, force: bool = False):
        now = time.monotonic()
        if not force and self.cached_affine is not None and (now - self.last_state_refresh) < STATE_REFRESH_INTERVAL:
            return

        model_extents = np.asarray(await self.remote_read("model.extents"), dtype=np.float32)
        perspective = await self.remote_read("view.perspective")
        view_extents = np.asarray(await self.remote_read("view.extents"), dtype=np.float32)
        affine = np.asarray(await self.remote_read("view.affine"), dtype=np.float32).reshape(4, 4)

        self.cached_model_extents = model_extents
        self.cached_perspective = bool(perspective)
        self.cached_view_extents = view_extents
        self.cached_affine = affine
        self.last_state_refresh = now

    async def update_client(self, event: MotionEvent | ButtonEvent):
        """
        This send mouse events over to the client. Currently just a few properties are used but more are avaialable:
        view.target, view.constructionPlane, view.extents, view.affine, view.perspective, model.extents, selection.empty, selection.extents, hit.lookat, views.front

        """
        if isinstance(event, ButtonEvent):
            await self.refresh_state(force=True)
            model_extents = self.cached_model_extents
            if model_extents is None:
                return
            await self.remote_write("view.affine", await self.remote_read("views.front"))
            await self.remote_write("view.extents", [c * 1.2 for c in model_extents])
            self.cached_affine = None
            self.cached_view_extents = None
            self.cached_perspective = None
            self.last_state_refresh = 0.0
            return

        trans_in, rot_in, dt = self.process_motion(event)

        await self.refresh_state(force=self.needs_resync)
        self.needs_resync = False
        model_extents = self.cached_model_extents
        view_extents = self.cached_view_extents
        curr_affine = self.cached_affine
        perspective = self.cached_perspective

        if model_extents is None or view_extents is None or curr_affine is None or perspective is None:
            return

        # This (transpose of top left quadrant) is the correct way to get the rotation matrix of the camera but it is unstable.. Either of the below methods works fine though.
        R_cam = curr_affine[:3, :3].T
        # cam2world = np.linalg.inv(curr_affine)
        # R_cam = cam2world[:3, :3]
        U, _, Vt = np.linalg.svd(R_cam)
        R_cam = U @ Vt

        # Scale movement relative to the current view volume so control remains
        # usable across both close-up and far-away navigation.
        extent_scale = max(float(np.linalg.norm(view_extents[3:6] - view_extents[0:3])), 1e-3)

        # 2) Separately calculate rotation and translation matrices
        angles = np.array([rot_in[0], rot_in[1], -rot_in[2]], dtype=np.float32) * (ROTATION_SPEED_DEG * dt)
        R_delta_cam = transform.Rotation.from_euler("xyz", angles, degrees=True).as_matrix()
        R_world = R_cam @ R_delta_cam @ R_cam.T

        rot_delta = np.eye(4, dtype=np.float32)
        rot_delta[:3, :3] = R_world
        trans_delta = np.eye(4, dtype=np.float32)
        trans_delta[3, :3] = np.array([-trans_in[0], -trans_in[2], trans_in[1]], dtype=np.float32) * (extent_scale * TRANSLATION_SPEED * dt)

        # 3) Apply changes to the ModelViewProjection matrix
        pivot_pos, pivot_neg = self.get_affine_pivot_matrices(model_extents)
        new_affine = trans_delta @ curr_affine @ (pivot_neg @ rot_delta @ pivot_pos)

        # Write back changes and optionally update extents if the projection is orthographic!
        if not perspective:
            zoom_delta = float(trans_in[1]) * ZOOM_SPEED * dt
            scale = float(np.clip(np.exp(zoom_delta), 0.9, 1.1))
            new_extents = (view_extents * scale).tolist()
            await self.remote_write("motion", True)
            await self.remote_write("view.extents", new_extents)
            self.cached_view_extents = np.asarray(new_extents, dtype=np.float32)
        else:
            await self.remote_write("motion", True)
        new_affine_list = new_affine.reshape(-1).tolist()
        await self.remote_write("view.affine", new_affine_list)
        self.cached_affine = np.asarray(new_affine_list, dtype=np.float32).reshape(4, 4)


async def create_mouse_controller(wamp_state_handler: WampSession, spacenav_reader: asyncio.StreamReader) -> Controller:
    """
    This takes in an active websocket wrapped in a wampsession, it consumes the first couple of messages that form a sort of pseudo handshake..
    When all is said is done it returns an active controller!
    """
    await wamp_state_handler.wamp.begin()
    logging.info("WAMP session started")
    # The first three messages are typically prefix setters!
    msg = await wamp_state_handler.wamp.next_message()
    while isinstance(msg, Prefix):
        logging.info("received prefix: %s -> %s", msg.prefix, msg.uri)
        await wamp_state_handler.wamp.run_message_handler(msg)
        msg = await wamp_state_handler.wamp.next_message()

    # The first call after the prefixes must be 'create mouse'
    assert isinstance(msg, Call)
    assert msg.proc_uri == "3dx_rpc:create" and msg.args[0] == "3dconnexion:3dmouse"
    mouse = Mouse3d()  # There is really no point to this lol
    logging.info(f'Created 3d mouse "{mouse.id}" for version {msg.args[1]}')
    await wamp_state_handler.wamp.send_message(CallResult(msg.call_id, {"connexion": mouse.id}))

    # And the second call after the prefixes must be 'create controller'
    msg = await wamp_state_handler.wamp.next_message()
    assert isinstance(msg, Call)
    assert msg.proc_uri == "3dx_rpc:create" and msg.args[0] == "3dconnexion:3dcontroller" and msg.args[1] == mouse.id
    metadata = msg.args[2]
    controller = Controller(spacenav_reader, mouse, wamp_state_handler, metadata)
    logging.info(f'Created controller "{controller.id}" for mouse "{mouse.id}", for client "{metadata["name"]}", version "{metadata["version"]}"')

    await wamp_state_handler.wamp.send_message(CallResult(msg.call_id, {"instance": controller.id}))
    return controller
