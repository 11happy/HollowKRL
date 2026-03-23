import time
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from stable_baselines3.common.callbacks import CheckpointCallback
from stable_baselines3.common.monitor import Monitor
from env import HollowKnightEnv
import numpy as np

CHECKPOINT   = "/home/happy/hk_agent/checkpoints_2/ppo_hornet_3_360000_steps.zip"  
VECNORM      = "/home/happy/hk_agent/checkpoints_2/ppo_hornet_3_vecnormalize_360000_steps.pkl"    

print("Loading checkpoint...")

env = DummyVecEnv([lambda: Monitor(HollowKnightEnv())])

env = VecNormalize.load(VECNORM, env)
env.norm_obs    = True
env.norm_reward = True
env.clip_obs    = np.inf
env.clip_reward = np.inf
env.training    = True   


model = PPO.load(CHECKPOINT, env=env,device="cpu")

checkpoint_cb = CheckpointCallback(
    save_freq   = 10_000,
    save_path   = "./checkpoints_2/",
    name_prefix = "ppo_hornet_3c",
)

print("Resuming in 5 seconds — focus HK window...")
time.sleep(5)

model.learn(
    total_timesteps     = 1000000,
    callback            = checkpoint_cb,
    reset_num_timesteps = False, 
    tb_log_name         = "ppo_hornet_3c",
)

model.save("checkpoints_2/ppo_hornet_3c_final")
env.save("checkpoints_2/ppo_hornet_3c_vecnormalize_final.pkl")
print("Done.")
