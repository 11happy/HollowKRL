## Observation space

Box(16,) float32:

    0  player_hp
    1  player_max_hp
    2  player_vx
    3  player_vy
    4  on_ground          (0/1)
    5  boss_hp
    6  boss_max_hp
    7  dx                 (boss_x - player_x)
    8  dy                 (boss_y - player_y)
    9  boss_vx
    10 boss_vy
    11 threat_active      (0/1)
    12 threat_dx          (nearest needle/sphere ball)
    13 threat_dy
    14 threat_vx
    15 threat_vy


## Action space

Discrete(8):

    0  idle
    1  left
    2  right
    3  jump            (z)
    4  right + jump
    5  left + jump
    6  left + attack   (x)
    7  right + attack

Jump actions hold for 225ms, others for 50ms.

## Reward

Terminal:

    boss killed   -> +300 + 25 * player_hp
    player died   -> -300

Per-step:

    boss damage dealt   -> +30 * (1 + player_hp_frac)
    player damage taken -> -30 * (1 + (1 - player_hp_frac))
    dodged near threat  -> +2     (prev_dist < 4 and now increasing)
    move action, no vx  -> -1     (penalize stuck movement)
    time penalty        -> -0.1


## MOD
 mod streams JSON lines over a TCP socket on port 11000. The Python env connects as a
client