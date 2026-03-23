import gymnasium as gym
from gymnasium import spaces
import numpy as np
import socket
import json
import subprocess
import time
from pynput.keyboard import Key, KeyCode, Controller

keyboard = Controller()


ACTION_MAP = {
    0: None,                                          # idle
    1: [Key.left],                                    # left
    2: [Key.right],                                   # right
    3: [KeyCode.from_char('z')],                      # jump
    4: [Key.right, KeyCode.from_char('z')],           # right + jump
    5: [Key.left,  KeyCode.from_char('z')],           # left + jump
    6: [Key.left,  KeyCode.from_char('x')],           # left + attack
    7: [Key.right, KeyCode.from_char('x')],           # right + attack
}

JUMP_ACTIONS  = {3, 4, 5}
JUMP_DURATION = 0.225
STEP_DELAY    = 0.05
TELEPORT_KEY  = '2'


_HK_WIN_ID = None

def get_hk_window_id():
    global _HK_WIN_ID
    if _HK_WIN_ID is None:
        result = subprocess.run(
            ["xdotool", "search", "--name", "Hollow Knight"],
            capture_output=True, text=True
        )
        _HK_WIN_ID = result.stdout.strip().split("\n")[0]
    return _HK_WIN_ID

def focus_hk():
    win_id = get_hk_window_id()
    subprocess.run(["xdotool", "windowfocus", win_id],
                   capture_output=True)
    time.sleep(0.025)


class HollowKnightEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, host='localhost', port=11000):
        super().__init__()

        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(16,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(8)

        self.host = host
        self.port = port
        self.sock = None
        self.buf  = b""

        self.prev_boss_hp     = None
        self.prev_player_hp   = None
        self.prev_threat_dist = None
        self.prev_player_vx   = None
        self.steps            = 0
        self.max_steps        = 2000

        self._connect()


    def _connect(self):
        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.connect((self.host, self.port))
                self.sock.setblocking(True)
                self.buf = b""
                print("Connected to mod")
                return
            except ConnectionRefusedError:
                print("Waiting for mod...")
                time.sleep(1.0)

    def _reconnect(self):
        print("Reconnecting to mod...")
        try:
            self.sock.close()
        except:
            pass
        self.sock = None
        self.buf  = b""
        time.sleep(2.0)
        self._connect()

    def _read_fresh_state(self):
        try:
            self.sock.setblocking(False)
            latest = None
            try:
                while True:
                    chunk = self.sock.recv(65536)
                    if chunk:
                        self.buf += chunk
            except BlockingIOError:
                pass
            self.sock.setblocking(True)

            while b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                try:
                    latest = json.loads(line)
                except:
                    pass

            if latest is not None:
                return latest

            while b"\n" not in self.buf:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Mod disconnected")
                self.buf += chunk

            line, self.buf = self.buf.split(b"\n", 1)
            return json.loads(line)

        except (ConnectionError, OSError):
            self._reconnect()
            return self._read_fresh_state()


    def _state_to_obs(self, state):
        return np.array([
            state["player_hp"],
            state["player_max_hp"],
            state["player_vx"],
            state["player_vy"],
            float(state["on_ground"]),
            state["boss_hp"],
            state["boss_max_hp"],
            state["dx"],
            state["dy"],
            state["boss_vx"],
            state["boss_vy"],
            float(state["threat_active"]),
            state["threat_dx"],
            state["threat_dy"],
            state["threat_vx"],
            state["threat_vy"],
        ], dtype=np.float32)

    def _compute_reward(self, state, action):
        boss_dead = (
            self.prev_boss_hp is not None and
            self.prev_boss_hp > 0 and
            state["boss_hp"] <= 0 and
            state["boss_max_hp"] > 0
        )
        player_dead = state["player_hp"] <= 0

        if boss_dead:   return  (300.0 + state["player_hp"]*25)
        if player_dead: return -300

        reward = 0.0

        if self.prev_boss_hp is not None:
            boss_dmg = self.prev_boss_hp - state["boss_hp"]
            if boss_dmg > 0:
                hp_factor =  state["player_hp"] / max (state["player_max_hp"],1)
                reward += 20.0 *(1+hp_factor)


        if self.prev_player_hp is not None:
            player_dmg = self.prev_player_hp - state["player_hp"]
            if player_dmg > 0:
                hp_factor = 1 + (1 - (state["player_hp"]/max(state["player_max_hp"],1)))
                reward -= 20.0*hp_factor

        if state["threat_active"]:
            curr_threat_dist = np.hypot(state["threat_dx"],state["threat_dy"])
            if self.prev_threat_dist is not None:
                if self.prev_threat_dist < 4.0 and curr_threat_dist > self.prev_threat_dist:
                    reward+=2.0
            self.prev_threat_dist = curr_threat_dist
        else:
            self.prev_threat_dist = None

        if action in (1, 5, 6) and abs(state["player_vx"]) < 0.05:
            reward -= 1.0
        if action in (2, 4, 7) and abs(state["player_vx"]) < 0.05:
            reward -= 1.0
        self.prev_player_vx = state["player_vx"]

        reward -= 0.1

        return reward

    def _send_action(self, action):
        focus_hk()
        keys = ACTION_MAP[action]

        if keys is None:
            time.sleep(STEP_DELAY)
            return

        for k in keys:
            keyboard.press(k)

        time.sleep(JUMP_DURATION if action in JUMP_ACTIONS else STEP_DELAY)

        for k in keys:
            keyboard.release(k)

    def _release_all(self):
        for keys in ACTION_MAP.values():
            if keys is None:
                continue
            for k in keys:
                try:
                    keyboard.release(k)
                except:
                    pass

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)

        self._release_all()
        focus_hk()
        time.sleep(4.0)

        try:
            self.sock.getpeername()
        except OSError:
            self._reconnect()

        keyboard.press(KeyCode.from_char(TELEPORT_KEY))
        time.sleep(STEP_DELAY)
        keyboard.release(KeyCode.from_char(TELEPORT_KEY))
        time.sleep(3.0)

        state = self._read_fresh_state()

        self.prev_boss_hp     = state["boss_hp"]
        self.prev_player_hp   = state["player_hp"]
        self.prev_threat_dist = None
        self.prev_player_vx   = None
        self.steps            = 0

        return self._state_to_obs(state), {}

    def step(self, action):
        self._send_action(action)
        state = self._read_fresh_state()

        reward = self._compute_reward(state, action)

        player_dead = state["player_hp"] <= 0
        boss_dead   = (
            self.prev_boss_hp is not None and
            self.prev_boss_hp > 0 and
            state["boss_hp"] <= 0 and
            state["boss_max_hp"] > 0
        )

        terminated = player_dead or boss_dead
        truncated  = self.steps >= self.max_steps

        self.prev_boss_hp   = state["boss_hp"]
        self.prev_player_hp = state["player_hp"]
        self.steps         += 1

        return self._state_to_obs(state), reward, terminated, truncated, {}

    def close(self):
        self._release_all()
        if self.sock:
            self.sock.close()